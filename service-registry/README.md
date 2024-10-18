```sh
protoc --go_out=registry --go_opt=paths=source_relative \
    --go-grpc_out=registry --go-grpc_opt=paths=source_relative registry.proto
```
