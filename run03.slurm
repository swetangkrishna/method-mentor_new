#!/bin/bash
#SBATCH --job-name=s03_experiment
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --gres=gpu:1
#SBATCH --time=1-00:00

cd /home/skrishna/method-mentor-main/method-mentor-new

python run_experiment.py --scenario S03 --runs 5 > output7_stages_included.log 2>&1