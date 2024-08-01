#!/bin/bash
# build_and_push.sh
REGION=$(terraform output -raw region)
REPO_URL=$(terraform output -raw ecr_repository_url)

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $REPO_URL
docker build -t $REPO_URL:latest ./build
docker push $REPO_URL:latest