#!/bin/bash


# Activate your environment, if necessary
# source /path/to/your/venv/bin/activate

cd ${HOME}/splatoon-x-rss

# Run your Python script
conda run -n splatoon-x-rss python run.py

# Navigate to the docs directory
cd docs

# Check for changes
git add .

# If there are changes, commit and push
if [[ `git status --porcelain` ]]; then
  git commit -m "Update docs"
  git push origin main
else
  echo "No changes to commit."
fi
