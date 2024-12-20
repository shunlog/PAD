// Code generated by protoc-gen-go-grpc. DO NOT EDIT.
// versions:
// - protoc-gen-go-grpc v1.5.1
// - protoc             v5.28.2
// source: registry.proto

package registry

import (
	context "context"
	grpc "google.golang.org/grpc"
	codes "google.golang.org/grpc/codes"
	status "google.golang.org/grpc/status"
)

// This is a compile-time assertion to ensure that this generated file
// is compatible with the grpc package it is being compiled against.
// Requires gRPC-Go v1.64.0 or later.
const _ = grpc.SupportPackageIsVersion9

const (
	ServiceRegistry_RegisterService_FullMethodName     = "/registry.ServiceRegistry/RegisterService"
	ServiceRegistry_GetServiceInstances_FullMethodName = "/registry.ServiceRegistry/GetServiceInstances"
)

// ServiceRegistryClient is the client API for ServiceRegistry service.
//
// For semantics around ctx use and closing/ending streaming RPCs, please refer to https://pkg.go.dev/google.golang.org/grpc/?tab=doc#ClientConn.NewStream.
type ServiceRegistryClient interface {
	RegisterService(ctx context.Context, in *ServiceInfo, opts ...grpc.CallOption) (*RegisterResponse, error)
	GetServiceInstances(ctx context.Context, in *ServiceQuery, opts ...grpc.CallOption) (*ServiceInstances, error)
}

type serviceRegistryClient struct {
	cc grpc.ClientConnInterface
}

func NewServiceRegistryClient(cc grpc.ClientConnInterface) ServiceRegistryClient {
	return &serviceRegistryClient{cc}
}

func (c *serviceRegistryClient) RegisterService(ctx context.Context, in *ServiceInfo, opts ...grpc.CallOption) (*RegisterResponse, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(RegisterResponse)
	err := c.cc.Invoke(ctx, ServiceRegistry_RegisterService_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *serviceRegistryClient) GetServiceInstances(ctx context.Context, in *ServiceQuery, opts ...grpc.CallOption) (*ServiceInstances, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(ServiceInstances)
	err := c.cc.Invoke(ctx, ServiceRegistry_GetServiceInstances_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

// ServiceRegistryServer is the server API for ServiceRegistry service.
// All implementations must embed UnimplementedServiceRegistryServer
// for forward compatibility.
type ServiceRegistryServer interface {
	RegisterService(context.Context, *ServiceInfo) (*RegisterResponse, error)
	GetServiceInstances(context.Context, *ServiceQuery) (*ServiceInstances, error)
	mustEmbedUnimplementedServiceRegistryServer()
}

// UnimplementedServiceRegistryServer must be embedded to have
// forward compatible implementations.
//
// NOTE: this should be embedded by value instead of pointer to avoid a nil
// pointer dereference when methods are called.
type UnimplementedServiceRegistryServer struct{}

func (UnimplementedServiceRegistryServer) RegisterService(context.Context, *ServiceInfo) (*RegisterResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method RegisterService not implemented")
}
func (UnimplementedServiceRegistryServer) GetServiceInstances(context.Context, *ServiceQuery) (*ServiceInstances, error) {
	return nil, status.Errorf(codes.Unimplemented, "method GetServiceInstances not implemented")
}
func (UnimplementedServiceRegistryServer) mustEmbedUnimplementedServiceRegistryServer() {}
func (UnimplementedServiceRegistryServer) testEmbeddedByValue()                         {}

// UnsafeServiceRegistryServer may be embedded to opt out of forward compatibility for this service.
// Use of this interface is not recommended, as added methods to ServiceRegistryServer will
// result in compilation errors.
type UnsafeServiceRegistryServer interface {
	mustEmbedUnimplementedServiceRegistryServer()
}

func RegisterServiceRegistryServer(s grpc.ServiceRegistrar, srv ServiceRegistryServer) {
	// If the following call pancis, it indicates UnimplementedServiceRegistryServer was
	// embedded by pointer and is nil.  This will cause panics if an
	// unimplemented method is ever invoked, so we test this at initialization
	// time to prevent it from happening at runtime later due to I/O.
	if t, ok := srv.(interface{ testEmbeddedByValue() }); ok {
		t.testEmbeddedByValue()
	}
	s.RegisterService(&ServiceRegistry_ServiceDesc, srv)
}

func _ServiceRegistry_RegisterService_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(ServiceInfo)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(ServiceRegistryServer).RegisterService(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: ServiceRegistry_RegisterService_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(ServiceRegistryServer).RegisterService(ctx, req.(*ServiceInfo))
	}
	return interceptor(ctx, in, info, handler)
}

func _ServiceRegistry_GetServiceInstances_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(ServiceQuery)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(ServiceRegistryServer).GetServiceInstances(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: ServiceRegistry_GetServiceInstances_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(ServiceRegistryServer).GetServiceInstances(ctx, req.(*ServiceQuery))
	}
	return interceptor(ctx, in, info, handler)
}

// ServiceRegistry_ServiceDesc is the grpc.ServiceDesc for ServiceRegistry service.
// It's only intended for direct use with grpc.RegisterService,
// and not to be introspected or modified (even as a copy)
var ServiceRegistry_ServiceDesc = grpc.ServiceDesc{
	ServiceName: "registry.ServiceRegistry",
	HandlerType: (*ServiceRegistryServer)(nil),
	Methods: []grpc.MethodDesc{
		{
			MethodName: "RegisterService",
			Handler:    _ServiceRegistry_RegisterService_Handler,
		},
		{
			MethodName: "GetServiceInstances",
			Handler:    _ServiceRegistry_GetServiceInstances_Handler,
		},
	},
	Streams:  []grpc.StreamDesc{},
	Metadata: "registry.proto",
}
