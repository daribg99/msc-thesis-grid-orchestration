# 🚀 WORK IN PROGRESS — Thesis under development

This repository contains drafts, experiments and notes for the thesis. The work is actively in progress and will be updated regularly.

Status
- 🔧 In development
- 📅 Last updated: 22 December 2025

Folders content:
- `deploy/`: deployment for PDCs and PMUs
- `deploy_automation/`: script to automate deployment, including applier for topology-based configuration and cli for automatic configuration
- `modeling_algorithms/`: placement and visualization algorithms for PDCs
- `reinforcement-learning/`: testing RL algorithms for PDC placement 

# If you want to try the deployment...
- Go into deploy_automation folder
- make sure kubeconfigs folders is empty ( only for the first time )
- run 
```bash
./autopdc_configurator.py json_file
```
Note: you need k3d installed. As said before, this is a work in progress, so some parts of the code may not work as expected.