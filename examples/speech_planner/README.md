# Speech Planner Example

In this example, we showcase how to build an intelligent speech-to-speech voice assistant pipeline using nvidia-pipecat with Speech Planner capabilities. This pipeline uses a Websocket based ACETransport, Riva ASR and TTS models, and NVIDIA LLM Service with enhanced end-of-utterance detection. We recommend first following [the Pipecat documentation](https://docs.pipecat.ai/getting-started/core-concepts) or [the ACE Controller](https://docs.nvidia.com/ace/ace-controller-microservice/latest/user-guide.html#pipecat-overview) Pipecat overview section to understand core concepts.

## What is Speech Planner?

`SpeechPlanner` enables intelligent end of utterance detection by using acoustic signals in addition to semantic information, enabling early triggers to LLM and TTS services. This results in more natural conversation flow and reduced latency by intelligently detecting when a user has finished speaking, even before traditional VAD (Voice Activity Detection) would typically trigger.

## Prerequisites

1. Copy and configure the environment file:
   ```bash
   cp env.example .env  # and add your credentials
   ```

2. Ensure you have the required API keys:
   - NVIDIA_API_KEY - Required for accessing NIM ASR, TTS and LLM models
   - (Optional) ZEROSHOT_TTS_NVIDIA_API_KEY - Required for zero-shot TTS

## Option 1: Deploy Using Docker

#### Prerequisites
- You have access and are logged into NVIDIA NGC. For step-by-step instructions, refer to [the NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account).

- You have access to an NVIDIA Volta™, NVIDIA Turing™, or an NVIDIA Ampere architecture-based A100 GPU. For more information, refer to [the Support Matrix](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/support-matrix.html#support-matrix).

- You have Docker installed with support for NVIDIA GPUs. For more information, refer to [the Support Matrix]((https://docs.nvidia.com/deeplearning/riva/user-guide/docs/support-matrix.html#support-matrix)).

From the examples/speech_planner directory, run below commands:

```bash
docker compose up -d
```

## Option 2: Deploy using Python environment

#### Prerequisites
From the examples/speech_planner directory, run the following commands to create a virtual environment and install the dependencies:

```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv sync
```

Make sure you've configured the `.env` file with your API keys before proceeding.

After making all required changes/customizations in bot.py, you can deploy the pipeline using below command:

```bash
python bot.py
```

## Using Speech Planner

By default, Speech Planner will use the `./prompt.yaml` file for configurations such as `using_chat_history` and `prompts`. 

**Recommended Setup:**
- Local NIM is recommended for Speech Planner for optimal performance
- Connect to the local NIM using `base_url` parameter in `SpeechPlanner`
- Pass the parameter `context` and `context_window` to `SpeechPlanner` service for maintaining chat history

## Start interacting with the application

This will host the static web client along with the ACE controller server, visit `http://WORKSTATION_IP:8100/static/index.html` in your browser to start a session.

Note: For mic access, you will need to update chrome://flags/ and add http://WORKSTATION_IP:8100 in Insecure origins treated as secure section.

If you want to update the port, make changes in the `uvicorn.run` command in [the bot.py](bot.py) and the `wsUrl` in [the static/index.html](../static/index.html).

## Bot customizations

### Speech Planner Specific Configurations

When using Speech Planner, you can customize the behavior through the `prompt.yaml` configuration file:

- **using_chat_history**: Enable/disable chat history context for better utterance detection
- **prompts**: Customize the prompts used by Speech Planner for semantic analysis
- **context_window**: Configure the context window size for maintaining conversation history

#### Example: Switching to the Llama 3.3-70B Model

To use larger LLMs like Llama 3.3-70B model in your deployment, you need to update both the Docker Compose configuration and the environment variables for your Python application. Follow these steps:

- In your `docker-compose.yml` file, find the `nvidia-llm` service section.
- Change the NIM image to 70B model: `nvcr.io/nim/meta/llama-3.3-70b-instruct:latest`
- Update the `device_ids` to allocate at least two GPUs (for example, `['2', '3']`).
- Update the environment variable under python-app service to `NVIDIA_LLM_MODEL=meta/llama-3.3-70b-instruct`

#### Setting up Zero-shot Magpie Latest Model

Follow these steps to configure and use the latest Zero-shot Magpie TTS model:

1. **Update Docker Compose Configuration**

Modify the `riva-tts-magpie` service in your docker-compose file with the following configuration:

```yaml
 riva-tts-magpie:
  image: <magpie-tts-zeroshot-image:version>  # Replace this with the actual image tag
  environment:
    - NGC_API_KEY=${ZEROSHOT_TTS_NVIDIA_API_KEY}
    - NIM_HTTP_API_PORT=9000
    - NIM_GRPC_API_PORT=50051
  ports:
    - "49000:50051"
  shm_size: 16GB
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ['0']
            capabilities: [gpu]
```

- Ensure your ZEROSHOT_TTS_NVIDIA_API_KEY key is properly set in your `.env` file:
  ```bash
  ZEROSHOT_TTS_NVIDIA_API_KEY=
  ```

2. **Configure TTS Voice Settings**

Update the following environment variables under the `python-app` service:

```bash
RIVA_TTS_VOICE_ID=Magpie-ZeroShot.Female-1
RIVA_TTS_MODEL=magpie_tts_ensemble-Magpie-ZeroShot
```

3. **Zero-shot Audio Prompt Configuration**

To use a custom voice with zero-shot learning:

- Add your audio prompt file to the workspace
- Mount the audio file into your container by adding a volume in your `docker-compose.yml` under the `python-app` service:
  ```yaml
  services:
    python-app:
      # ... existing code ...
      volumes:
        - ./audio_prompts:/app/audio_prompts
  ```
- Set the `ZERO_SHOT_AUDIO_PROMPT` environment variable to the path relative to your application root:
  ```yaml
  environment:
    - ZERO_SHOT_AUDIO_PROMPT=audio_prompts/voice_sample.wav  # Path relative to app root
  ```

Note: The zero-shot audio prompt is only required when using the Magpie Zero-shot model. For standard Magpie multilingual models, this configuration should be omitted.
