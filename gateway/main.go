package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	pb "gateway/registry"

	"google.golang.org/grpc"
)

const (
	// Time to wait for a response from a service
	REQUEST_TIMEOUT = 500 * time.Millisecond
	
    REGISTRY_ADDR = "service-registry:50051"
	// Circuit breaker
	N_RETRIES = 2  // Number of retries before circuit-breaking an instance
	N_INSTANCES_TRIED = 2  // number of instances failed before returning error

	// Cooldown period for querying the service registry
	COOLDOWN_T = time.Second * 10
	// Cooldown period after blocking an instance
	BLOCKED_T = time.Second * 20
)

var (
    // Cache to store last call timestamps for service queries
    serviceCache = make(map[string]cachedServiceInfo)
    mu           sync.Mutex // Mutex to protect access to the cache

	blocked = make(map[*pb.ServiceInfo]time.Time)
	blocked_mu  sync.Mutex // Mutex for `blocked` map
)

type cachedServiceInfo struct {
    instances []*pb.ServiceInfo
    lastCall  time.Time
}

// Function to query the registry for service instances and return them
func queryServiceInstances(client pb.ServiceRegistryClient, serviceName string) []*pb.ServiceInfo {
    mu.Lock()
    cachedInfo, exists := serviceCache[serviceName]
    mu.Unlock()

    // Check if the cached value is still valid
    if exists && time.Since(cachedInfo.lastCall) < COOLDOWN_T {
        return cachedInfo.instances // Return cached instances
    }

    ctx, cancel := context.WithTimeout(context.Background(), time.Second*5)
    defer cancel()

    // Create the ServiceQuery for the specific service
    query := &pb.ServiceQuery{ServiceName: serviceName}

    // Call GetServiceInstances to fetch the registered instances
    resp, err := client.GetServiceInstances(ctx, query)
    if err != nil {
        log.Printf("Error calling GetServiceInstances: %v", err)
        return nil
    }

    // Cache the new instances and update the last call timestamp
    mu.Lock()
    serviceCache[serviceName] = cachedServiceInfo{
        instances: resp.Instances,
        lastCall:  time.Now(),
    }
    mu.Unlock()

    // Return the list of service instances
    return resp.Instances
}

var roundRobinIndex = 0 // Track the index for round-robin selection

func selectServiceInstance(instances []*pb.ServiceInfo) *pb.ServiceInfo {
    if len(instances) == 0 {
        return nil
    }

	// unblock instances if time has passed
	blocked_mu.Lock()
	for inst, t := range blocked {
        if time.Since(t) > BLOCKED_T {
            delete(blocked, inst)
        }
    }
	blocked_mu.Unlock()
	
	// select next non-blocked instance
	for range len(instances){
		selectedInstance := instances[roundRobinIndex]
		roundRobinIndex = (roundRobinIndex + 1) % len(instances)

		// Check if instance is not blocked
		is_blocked := false
		blocked_mu.Lock()
		for inst := range blocked {
			if inst == selectedInstance {
				is_blocked = true
			}
		}
		blocked_mu.Unlock()
		if !is_blocked {
			return selectedInstance
		}
		// Selected instance is bocked, try next
	}

	// All instances are blocked
	return nil
}


// HTTP handler to proxy requests to a service instance
func proxyHandler(client pb.ServiceRegistryClient) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        // Parse the request URL to extract the service name
        pathParts := strings.SplitN(r.URL.Path, "/", 3)
        if len(pathParts) < 3 {
            http.Error(w, "Invalid request format. Expected /service-name/endpoint", http.StatusBadRequest)
            return
        }

        serviceName := pathParts[1] // The first part is the service name
        endpointPath := "/" + pathParts[2] // The rest is the actual endpoint

        // Query the service registry for available instances
        instances := queryServiceInstances(client, serviceName)		
		for range N_INSTANCES_TRIED {
			
			// Select an instance to forward the request to
			instance := selectServiceInstance(instances)
			if instance == nil {
				http.Error(w, "Failed to reach service instance", 500)
				log.Printf("No instances available for service %s\n", serviceName)
				return
			}
			
			for range N_RETRIES {
				err := proxyToInstance(instance, endpointPath, w, r)
				if err == nil {
					// Proxied successfully
					return
				}
			}

			// All requests to instnce failed, block it temporarily
			blocked_mu.Lock()
			blocked[instance] = time.Now()
			blocked_mu.Unlock()
			log.Printf("Instance %s failed %v times, blocking it", instance, N_RETRIES)
		}
		
		// Couldn't proxy N times to M instances 
		http.Error(w, "Failed to reach service instance", 500)
	}
}

func proxyToInstance(instance *pb.ServiceInfo, endpointPath string, w http.ResponseWriter, r *http.Request) error {
	
	// Proxy the request to the selected service instance
	proxyURL := fmt.Sprintf("http://%s%s", instance.Address, endpointPath)
	proxyReq, err := http.NewRequest(r.Method, proxyURL, r.Body)
	if err != nil {
		return errors.New("Failed to create proxy request")
	}

	// Forward the headers from the original request
	proxyReq.Header = r.Header

	// Perform the request
	client := &http.Client{
		Timeout: REQUEST_TIMEOUT,
	}
	resp, err := client.Do(proxyReq)
	if err != nil {
		return errors.New("Failed to reach service instance")
	}
	defer resp.Body.Close()
	
	// Copy the response back to the original client
	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return errors.New("Failed to read response body")
	}

	w.WriteHeader(resp.StatusCode)
	w.Write(body)
	return nil
}


type HealthCheckResponse struct {
    Status        string   `json:"status"`
}


func HealthCheckHandler(w http.ResponseWriter, r *http.Request) {
    data := HealthCheckResponse{Status: "Alive"}
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusCreated)
    json.NewEncoder(w).Encode(data)
}


func main() {
	log.Println("Connecting to Registry gRPC server on port 50051...")
    // Connect to the gRPC server
    conn, err := grpc.Dial(REGISTRY_ADDR, grpc.WithInsecure(), grpc.WithBlock())
    if err != nil {
        log.Fatalf("Failed to connect to registry: %v", err)
    }
    defer conn.Close()

    // Create a client for the ServiceRegistry
    client := pb.NewServiceRegistryClient(conn)

	// Start the HTTP server
	http.HandleFunc("/", proxyHandler(client))
    // Set up the HTTP server and routes
    http.HandleFunc("/status", HealthCheckHandler)


	log.Println("Starting HTTP server on port 5000...")
	log.Fatal(http.ListenAndServe(":5000", nil))

	
}
