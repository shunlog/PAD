package main

import (
	"context"
	"log"
	"net"
	"sync"
    "encoding/json"
    "net/http"
	
	"google.golang.org/grpc"
	pb "service-registry/registry"
)

// Set simulates a set using a map.
type Set map[string]struct{}

func NewSet() Set {
	return make(Set)
}

func (s Set) Add(element string) {
	s[element] = struct{}{} // Use the element as a key in the map to simulate a set
}

type Registry struct {
	pb.UnimplementedServiceRegistryServer
	mu       sync.RWMutex   // Mutex for synchronizing access
	services map[string]Set // service name -> set of addresses
}

func NewRegistry() *Registry {
	return &Registry{
		services: make(map[string]Set),
	}
}

// StatusResponse defines the structure of the health check response.
type StatusResponse struct {
    Status        string   `json:"status"`
    Services      []string `json:"services"`
    ServicesCount int      `json:"services_count"`
}

// StatusHandler returns the status and services in JSON format.
func (reg *Registry) StatusHandler(w http.ResponseWriter, r *http.Request) {
    reg.mu.RLock() // Acquire read lock
    defer reg.mu.RUnlock() // Ensure the lock is released

    // Prepare the response
    response := StatusResponse{
        Status:        "Alive",
        Services:      make([]string, 0, len(reg.services)),
        ServicesCount: 0,
    }

    // Iterate over the services to populate the response
    for serviceName, addresses := range reg.services {
        response.Services = append(response.Services, serviceName)
        response.ServicesCount += len(addresses) // Add count of service instances
    }

    // Set the response header and encode the response as JSON
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusOK)
    json.NewEncoder(w).Encode(response)
}



func (reg *Registry) AddService(serviceName, address string) {
	reg.mu.Lock()         // Lock for exclusive access
	defer reg.mu.Unlock() // Ensure the lock is released

	if _, exists := reg.services[serviceName]; !exists {
		reg.services[serviceName] = NewSet() // Create a new set for this service
	}
	reg.services[serviceName].Add(address) // Add the address to the set
}

func (reg *Registry) RegisterService(ctx context.Context, info *pb.ServiceInfo) (*pb.RegisterResponse, error) {
	reg.AddService(info.ServiceName, info.Address)
	return &pb.RegisterResponse{Success: true}, nil
}

func (reg *Registry) GetServices(serviceName string) Set {
	reg.mu.RLock()         // Acquire a read lock
	defer reg.mu.RUnlock() // Ensure the lock is released

	return reg.services[serviceName] // Return the set of addresses
}

func (reg *Registry) GetServiceInstances(ctx context.Context, req *pb.ServiceQuery) (*pb.ServiceInstances, error) {

	addresses := reg.GetServices(req.ServiceName)
	instances := &pb.ServiceInstances{
		Instances: make([]*pb.ServiceInfo, 0), // Initialize the slice for ServiceInfo
	}

	for address := range addresses {
		// Create a new ServiceInfo instance for each address
		serviceInfo := &pb.ServiceInfo{
			ServiceName: req.ServiceName,
			Address:     address,
		}
		instances.Instances = append(instances.Instances, serviceInfo) // Append the ServiceInfo to the list
	}
	return instances, nil
}

func main() {
	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer()
	reg := NewRegistry()                       // Initialize the ServiceRegistry instance
	pb.RegisterServiceRegistryServer(grpcServer, reg) // Use the initialized instance

    // Set up the HTTP server and routes
    http.HandleFunc("/status", reg.StatusHandler)
    go http.ListenAndServe(":8080", nil)

	
	log.Println("Service Registry running on port 50051")
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}

	
	
}
