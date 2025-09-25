# Riva Speech Langchain Example

This is an example that shows how to use `ACETransport` to communicate with Langchain. It supports `Nvidia Riva ASR and TTS`.

## Get Started

From the example directory, run the following commands to create a virtual environment and install the dependencies:

```bash
uv venv
uv sync
source .venv/bin/activate
```

Update the secrets in the `.env` file.

```bash
cp env.example .env # and add your credentials
```

## Deploy local Riva ASR and TTS models.

#### Prerequisites
- You have access and are logged into NVIDIA NGC. For step-by-step instructions, refer to [the NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account).

- You have access to an NVIDIA Volta™, NVIDIA Turing™, or an NVIDIA Ampere architecture-based A100 GPU. For more information, refer to [the Support Matrix](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/support-matrix.html#support-matrix).

- You have Docker installed with support for NVIDIA GPUs. For more information, refer to [the Support Matrix]((https://docs.nvidia.com/deeplearning/riva/user-guide/docs/support-matrix.html#support-matrix)).

#### Download Riva Quick Start

Go to the Riva Quick Start for [Data center](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/riva/resources/riva_quickstart/files?version=2.19.0). Select the File Browser tab to download the scripts or use [the NGC CLI tool](https://ngc.nvidia.com/setup/installers/cli) to download from the command line.

```bash
ngc registry resource download-version nvidia/riva/riva_quickstart:2.19.0
```

#### Deploy Riva Speech Server

From the example directory, run below commands:

```bash
cd riva_quickstart_v2.19.0
chmod +x riva_init.sh riva_clean.sh riva_start.sh
bash riva_clean.sh ../../utils/riva_config.sh
bash riva_init.sh ../../utils/riva_config.sh
bash riva_start.sh ../../utils/riva_config.sh
cd ..
```

This may take few minutes for the first time and will start the riva server on `localhost:50051`.

For more info, you can refer to the [Riva Quick Start Guide](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/quick-start-guide.html).


## Run the bot pipeline

```bash
python examples/riva_speech_langchain/bot.py
```

This will host the static web client along with the ACE controller server, visit `http://WORKSTATION_IP:8100/static/index.html` in your browser to start a session.

Note: For mic access, you will need to update chrome://flags/ and add http://WORKSTATION_IP:8100 in Insecure origins treated as secure section.