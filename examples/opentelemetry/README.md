# Auto instrumentation

To run the bot with auto-instrumentation use the following command:

```shell
$ uv sync --group examples
$ export OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true
$ opentelemetry-instrument \
  --traces_exporter console,otlp \
  --metrics_exporter console,otlp \
  --logs_exporter console,otlp \
  --service_name pipecat-opentelemetry \
  python3 bot.py
```

To receive the traces you will need to setup some kind of opentelemetry
collector. You can use Grafana's LGTM stack by running:

```shell
docker run -it -p 3000:3000 -p 4317:4317 -p 4318:4318 grafana/otel-lgtm
```

Once started navigate to the explore tab, then select Tempo as source
and click on the search tab.

You can now run the python application to generator a trace.
You should be able to see it in the search tab of Tempo.

You can configure the OTLP exporter with environment variables (
see [here](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/))

See python specific configuration
on [this page](https://opentelemetry.io/docs/zero-code/python/configuration/#python-specific-configuration)
