# ACE Controller Web UI

This is a web UI for the ACE Controller. Currently, it is only compatible with ACE Controller's "speech-to-speech" example.

## Running the Web UI

On the internal Gitlab CI, the web app is built and published as a downloadable artifact. Once downloaded, you can serve it from an HTTP server:

```bash
python -m http.server 8000
```

### Note

The build is configured to send the user's speech to the ACE Controller at a sample rate of 16 kHz. If your ACE Controller requires a different sample rate, you can change the `USER_SPEECH_SAMPLE_RATE` constant in `src/hooks/useMicrophone.ts`.

## Developping the Web UI

### Prerequisites

The web UI is built using ViteJS. To verify your system meets the prerequisites, run the following commands from the `web-ui` directory:

```bash
corepack enable
yarn -v # should return 4.7.0 or higher
node -v # should return v20 or higher
```

If your system doesn't meet these requirements, install [Node.js](https://nodejs.org/en/download) and try these commands again.

### Installation

```bash
yarn install
```

### Running a development server

```bash
yarn dev
```

This opens the web app in development mode. The app will automatically reload if you make changes to the code.

### Running tests

```bash
yarn test
```

### Building the web app

```bash
yarn build
```

This builds the app for production. The built files are in the `dist` directory.