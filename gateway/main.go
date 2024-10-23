package main

import (
    "context"
    "fmt"
    "io/ioutil"
    "log"
    "net/http"
    "strings"
    "time"

		"google.golang.org/grpc"
    pb "gateway/registry"  // Update with actual path to generated proto
)

const (
    registryAddress = "service-registry:50051" // Address of your Registry service
)

// Function to query the registry for service instances and return them
func queryServiceInstances(client pb.ServiceRegistryClient, serviceName string) []*pb.ServiceInfo {
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

    // Return the list of service instances
    return resp.Instances
}


var roundRobinIndex = 0 // Track the index for round-robin selection

func selectServiceInstance(instances []*pb.ServiceInfo) *pb.ServiceInfo {
    if len(instances) == 0 {
        return nil
    }

    // Select the instance at the current index
    selectedInstance := instances[roundRobinIndex]

    // Move to the next index, wrapping around if necessary
    roundRobinIndex = (roundRobinIndex + 1) % len(instances)

    return selectedInstance
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
        if len(instances) == 0 {
            http.Error(w, fmt.Sprintf("No instances available for service %s", serviceName), http.StatusServiceUnavailable)
            return
        }

        // Select an instance to forward the request to
        instance := selectServiceInstance(instances)
        if instance == nil {
            http.Error(w, fmt.Sprintf("No instances available for service %s", serviceName), http.StatusServiceUnavailable)
            return
        }

        // Proxy the request to the selected service instance
        proxyURL := fmt.Sprintf("http://%s%s", instance.Address, endpointPath)
        proxyReq, err := http.NewRequest(r.Method, proxyURL, r.Body)
        if err != nil {
            http.Error(w, "Failed to create proxy request", http.StatusInternalServerError)
            return
        }

        // Forward the headers from the original request
        proxyReq.Header = r.Header

        // Perform the request
        client := &http.Client{}
        resp, err := client.Do(proxyReq)
        if err != nil {
            http.Error(w, "Failed to reach service instance", http.StatusBadGateway)
            return
        }
        defer resp.Body.Close()

        // Copy the response back to the original client
        body, err := ioutil.ReadAll(resp.Body)
        if err != nil {
            http.Error(w, "Failed to read response body", http.StatusInternalServerError)
            return
        }

        w.WriteHeader(resp.StatusCode)
        w.Write(body)
    }
}


func main() {
    // Connect to the gRPC server
    conn, err := grpc.Dial(registryAddress, grpc.WithInsecure(), grpc.WithBlock())
    if err != nil {
        log.Fatalf("Failed to connect to registry: %v", err)
    }
    defer conn.Close()

    // Create a client for the ServiceRegistry
    client := pb.NewServiceRegistryClient(conn)

	// Start the HTTP server
		http.HandleFunc("/", proxyHandler(client))

	log.Println("Starting HTTP server on port 5000...")
	log.Fatal(http.ListenAndServe(":5000", nil))

		
}
