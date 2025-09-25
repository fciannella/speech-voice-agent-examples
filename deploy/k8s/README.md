# ACE Controller UCS Workflow

## Development
For building ACE Controller microservice locally
  ```bash
  ucf_ms_builder_cli service build -d ucs/
  ```

Review compliance results for the microservice at `ucs/output/compliance_test_logs.txt`. Check [UCF complaince documentation](https://docs.nvidia.com/ucf/text/UCS_ms_compliance.html) for more details.

Running test application for the microservice locally, run the below command.
  ```bash
  helm install test ucs/output/tests/dev-params1
  ```

## Staging
Before staging make sure you have updated versions in manifest.yaml. You will not able to overwrite existing microservice versions. Avoid using the same version tag for containers for different microservice versions, as Kubernetes might not use the latest container if the container is already present in the k8s registry.

- Staging microservice for Internal teams
  ```bash
  ucf_ms_builder_cli service build -d ucs/ --push
  ```

- Checking Complaince and Test application in Validation CI
  ```bash
  ucf_ms_builder_cli service validate -n ucf.svc.ace-controller -v <VERSION>
  ```


## Release

- For release make updates for all required versions and public container paths. Make sure microservices versions don't already exist in staging or prod ucf teams.

- Stage microservice and validate first. If everything works fine, push microservice to prod.
  ```bash
  ucf_ms_builder_cli service validate -n ucf.svc.ace-controller -v <VERSION> --push_to_prod
  ```


