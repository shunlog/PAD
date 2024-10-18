package main

import (
    "context"
    "fmt"
    "log"
    "time"

    "google.golang.org/grpc"
    pb "gateway/registry"  // Update with actual path to generated proto
)

const (
    registryAddress = "service-registry:50051" // Address of your Registry service
    serviceName     = "chat" // The service name you want to query
)

// Function to query the registry for service instances
func queryServiceInstances(client pb.ServiceRegistryClient, serviceName string) {
    ctx, cancel := context.WithTimeout(context.Background(), time.Second*5)
    defer cancel()

    // Create the ServiceQuery for the specific service
    query := &pb.ServiceQuery{ServiceName: serviceName}

    // Call GetServiceInstances to fetch the registered instances
    resp, err := client.GetServiceInstances(ctx, query)
    if err != nil {
        log.Printf("Error calling GetServiceInstances: %v", err)
        return
    }

    // Print the service instances
    fmt.Printf("Instances of service '%s':\n", serviceName)
    for _, instance := range resp.Instances {
        fmt.Printf("Service: %s, Address: %s\n", instance.ServiceName, instance.Address)
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

    // Query the service instances every 5 seconds
    ticker := time.NewTicker(5 * time.Second)
    defer ticker.Stop()

    // Loop that queries the service instances every 5 seconds
    for {
        queryServiceInstances(client, serviceName)
        <-ticker.C // Wait for the next tick (5 seconds)
    }
}
