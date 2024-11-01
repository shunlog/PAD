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

type ServiceRegistry struct {
	pb.UnimplementedServiceRegistryServer
	mu       sync.RWMutex   // Mutex for synchronizing access
	services map[string]Set // service name -> set of addresses
}

func NewServiceRegistry() *ServiceRegistry {
	return &ServiceRegistry{
		services: make(map[string]Set),
	}
}

// HealthCheckResponse defines the structure of the health check response.
type HealthCheckResponse struct {
    Status        string   `json:"status"`
    Services      []string `json:"services"`
    ServicesCount int      `json:"services_count"`
}

// HealthCheckHandler returns the status and services in JSON format.
func (sr *ServiceRegistry) HealthCheckHandler(w http.ResponseWriter, r *http.Request) {
    sr.mu.RLock() // Acquire read lock
    defer sr.mu.RUnlock() // Ensure the lock is released

    // Prepare the response
    response := HealthCheckResponse{
        Status:        "Alive",
        Services:      make([]string, 0, len(sr.services)),
        ServicesCount: 0,
    }

    // Iterate over the services to populate the response
    for serviceName, addresses := range sr.services {
        response.Services = append(response.Services, serviceName)
        response.ServicesCount += len(addresses) // Add count of service instances
    }

    // Set the response header and encode the response as JSON
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusOK)
    json.NewEncoder(w).Encode(response)
}



func (s *ServiceRegistry) AddService(serviceName, address string) {
	s.mu.Lock()         // Lock for exclusive access
	defer s.mu.Unlock() // Ensure the lock is released

	if _, exists := s.services[serviceName]; !exists {
		s.services[serviceName] = NewSet() // Create a new set for this service
	}
	s.services[serviceName].Add(address) // Add the address to the set
}

func (s *ServiceRegistry) RegisterService(ctx context.Context, info *pb.ServiceInfo) (*pb.RegisterResponse, error) {
	s.AddService(info.ServiceName, info.Address)
	return &pb.RegisterResponse{Success: true}, nil
}

func (s *ServiceRegistry) GetServices(serviceName string) Set {
	s.mu.RLock()         // Acquire a read lock
	defer s.mu.RUnlock() // Ensure the lock is released

	return s.services[serviceName] // Return the set of addresses
}

func (s *ServiceRegistry) GetServiceInstances(ctx context.Context, req *pb.ServiceQuery) (*pb.ServiceInstances, error) {

	addresses := s.GetServices(req.ServiceName)
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
	registry := NewServiceRegistry()                       // Initialize the ServiceRegistry instance
	pb.RegisterServiceRegistryServer(grpcServer, registry) // Use the initialized instance

    // Set up the HTTP server and routes
    http.HandleFunc("/status", registry.HealthCheckHandler)
    go http.ListenAndServe(":8080", nil)

	
	log.Println("Service Registry running on port 50051")
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}

	
	
}
