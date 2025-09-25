
ACE Controller
==============================

## Description

**ACE Controller**

The ACE Controller is a microservice utilizing the Python-based open-source [Pipecat framework](https://github.com/pipecat-ai/pipecat) for building real-time, voice-enabled, and multimodal conversational AI agents. Pipecat uses a pipeline-based architecture to handle real-time AI processing and handles the complex orchestration of AI services, network transport, audio processing, and multimodal interactions, letting you focus on creating engaging experiences.

The ACE Controller microservice extends the Pipecat framework to enable developers to easily customize, debug, and deploy complex pipelines along with the integration of powerful NVIDIA Services to the Pipecat ecosystem. The ACE Controller UCS microservice can connect with Riva Speech, Animgraph, Audio2Face, and SDR(Stream Distribution and Routing) UCS microservices.

## Usage

### Params:
ACE Controller microservice expects developers to build a custom docker image containing their pipeline and to update UCS microservice parameters.
```
ace-controller:

  # Configure custom docker image built for your pipeline/example
  image: "" # Custom docker image repository path
  tag: "" # Tag for custom docker image

  # OpenTelemetry configurations for ACE Controller and default settings
  OTEL_SDK_DISABLED: 'false' # When enabled, tracing data will be exported
  OTEL_SERVICE_NAME: ace-controller # Service name used for exporting OTel data
  OTEL_EXPORTER_OTLP_ENDPOINT: "" # Endpoint for Otel collector
  OTEL_EXPORTER_OTLP_PROTOCOL: grpc # Protocol for exporting OTel data
  
```

The custom docker image must contain the source code of your pipeline under the `/app` directory and a script for running the pipeline must be located at `/app/entrypoint.sh`.

### Connections:
Most of the connections are optional and you can use them based on your use case.

```
connections:
  ace-controller/redis: redis-timeseries/redis
  # Riva Speech GRPC endpoint
  ace-controller/riva-speech: riva-speech-endpoint/endpoint
  # Animation Graph HTTP endpoint
  ace-controller/animgraph-http: anim-graph-sdr/http-envoy
  # Animation Graph GRPC endpoint
  ace-controller/animgraph-grpc: anim-graph-sdr/grpc-envoy
  # Audio2Facd GRPC endpoint
  ace-controller/a2f-grpc: a2f-endpoint/endpoint
  # SDR connection for ACE Controller
  ace-controller-sdr/ace-controller: ace-controller/http-api
```

### Secrets
The ACE Controller microservice supports secrets for configuring the NVIDIA API Key, the OpenAI API Key, and the ElevenLabs API Key. Configured secrets will be mounted as a file and will be loaded as environment variables by the Microservice.

```
secrets:
  k8sSecret/nvidia-api-key-secret/NVIDIA_API_KEY:
    k8sSecret:
      secretName: nvidia-api-key-secret
      key: NVIDIA_API_KEY
  k8sSecret/openai-key-secret/OPENAI_API_KEY:
    k8sSecret:
      secretName: openai-key-secret
      key: OPENAI_API_KEY
  k8sSecret/custom-env-secrets/ENV:
    k8sSecret:
      secretName: custom-env-secrets
      key: ENV
```

**custom-env-secrets**: This secret can be used to pass any key-value pairs that will be exported as environment variables. This secret will mounted as file `/secrets/custom.env` and will be sourced before running services to set the environment variables.

```
cat <<EOF | tee custom.env
KEY1=VALUE1
KEY2=VALUE2
EOF

kubectl create secret generic custom-env-secrets --from-file=ENV=custom.env
```

## Performance
The performance of the microservice depends on the configured pipeline. Each instance of the microservice utilizes a single core process and might only be able to support a single user stream per pod for complex pipelines (e.g., driving a multimodal interactive avatar), but it can support multiple streams for simple pipelines (e.g., simple voice bot).

## Supported Platforms
- CPU: x86 compatible
- Linux (e.g. Ubuntu 22.04)

## Deployment requirements
- Make sure K8S foundational services are running.
- Local path provisioner service is installed.

## License
Check [LICENSE.txt](./LICENSE.txt)

## Known Issues / Limitations
NA

## References
- [ACE Controller Documentation](https://docs.nvidia.com/ace/ace-controller-microservice/latest/index.html)
- [Pipecat Documentation](https://docs.pipecat.ai/getting-started/overview)