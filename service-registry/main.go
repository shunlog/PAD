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

// This is a gRPC server type, which holds a map of services inside
type Registry struct {
	// not sure how to avoid this line
	pb.UnimplementedServiceRegistryServer
	mu       sync.RWMutex
	services map[string][]string // service name -> set of addresses
}

func NewRegistry() *Registry {
	return &Registry{
		services: make(map[string][]string),
	}
}


func (reg *Registry) AddService(serviceName, address string) {
	reg.mu.Lock()
	defer reg.mu.Unlock()

	if _, exists := reg.services[serviceName]; !exists {
		// reserve a realistic capacity for the array to avoid too many reallocations
		reg.services[serviceName] = make([]string, 0, 8)
	}
			
	reg.services[serviceName] = append(reg.services[serviceName], address)
}

func (reg *Registry) RegisterService(ctx context.Context, info *pb.ServiceInfo) (*pb.RegisterResponse, error) {
	reg.AddService(info.ServiceName, info.Address)
	return &pb.RegisterResponse{Success: true}, nil
}

func (reg *Registry) GetServices(serviceName string) []string {
	reg.mu.RLock()
	defer reg.mu.RUnlock()
	return reg.services[serviceName]
}

func (reg *Registry) GetServiceInstances(ctx context.Context, req *pb.ServiceQuery) (*pb.ServiceInstances, error) {

	addresses := reg.GetServices(req.ServiceName)
	instances := &pb.ServiceInstances{
		Instances: make([]*pb.ServiceInfo, 0),
	}

	for _, address := range addresses {
		serviceInfo := &pb.ServiceInfo{
			ServiceName: req.ServiceName,
			Address:     address,
		}
		instances.Instances = append(instances.Instances, serviceInfo)
	}
	return instances, nil
}


// JSON structure for the /status endpoint
type StatusResponse struct {
	Status        string   `json:"status"`
	Services      []string `json:"services"`
	ServicesCount int      `json:"services_count"`
}


func (reg *Registry) StatusHandler(w http.ResponseWriter, r *http.Request) {
	reg.mu.RLock()
	defer reg.mu.RUnlock()

	response := StatusResponse{
		Status:        "Alive",
		Services:      make([]string, 0, len(reg.services)),
		ServicesCount: 0,
	}

	for serviceName, addresses := range reg.services {
		response.Services = append(response.Services, serviceName)
		response.ServicesCount += len(addresses)
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(response)
}



func main() {
	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}
	grpcServer := grpc.NewServer()
	reg := NewRegistry()
	pb.RegisterServiceRegistryServer(grpcServer, reg)
	
	http.HandleFunc("/status", reg.StatusHandler)
	go http.ListenAndServe(":8080", nil)
	log.Println("HTTP server running on port 8080")

	log.Println("gRPC server running on port 50051")	
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}
}
