SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

PROJECT_DIR := cbb-upsets

.PHONY: infra-loop infra-loop-up infra-loop-status infra-loop-stop

infra-loop: infra-loop-up

infra-loop-up infra-loop-status infra-loop-stop:
	$(MAKE) -C $(PROJECT_DIR) $@
