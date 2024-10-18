package main

import (
    "context"
    "log"
    "net"
    "sync"

    "google.golang.org/grpc"
    pb "example/docker-ping/registry"
)

type registryServer struct {
    pb.UnimplementedServiceRegistryServer
    services map[string][]*pb.ServiceInfo
    mu       sync.Mutex
}

func (s *registryServer) RegisterService(ctx context.Context, info *pb.ServiceInfo) (*pb.RegisterResponse, error) {
    s.mu.Lock()
    defer s.mu.Unlock()

    s.services[info.ServiceName] = append(s.services[info.ServiceName], info)
    return &pb.RegisterResponse{Success: true}, nil
}

func (s *registryServer) GetServiceInstances(ctx context.Context, query *pb.ServiceQuery) (*pb.ServiceInstances, error) {
    s.mu.Lock()
    defer s.mu.Unlock()

    instances := s.services[query.ServiceName]
    return &pb.ServiceInstances{Instances: instances}, nil
}

func main() {
    lis, err := net.Listen("tcp", ":50051")
    if err != nil {
        log.Fatalf("failed to listen: %v", err)
    }

    grpcServer := grpc.NewServer()
    pb.RegisterServiceRegistryServer(grpcServer, &registryServer{services: make(map[string][]*pb.ServiceInfo)})

    log.Println("Service Registry running on port 50051")
    if err := grpcServer.Serve(lis); err != nil {
        log.Fatalf("failed to serve: %v", err)
    }
}
