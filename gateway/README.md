```
protoc -I ../protos --go_out=registry --go_opt=paths=source_relative \
  --go_opt=M../protos/registry.proto=gateway/registry \
  --go-grpc_out=registry --go-grpc_opt=paths=source_relative ../protos/registry.proto
```