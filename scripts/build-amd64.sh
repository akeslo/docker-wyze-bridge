#!/bin/bash
set -e

# Build and push script for AMD64 architecture only

IMAGE_NAME="${IMAGE_NAME:-ghcr.io/akeslo/docker-wyze-bridge}"
TAG="${TAG:-latest}"
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
GITHUB_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "local")

echo "Building and pushing Docker image for AMD64..."
echo "Image: ${IMAGE_NAME}:${TAG}"
echo "Platform: linux/amd64"
echo "Build Date: ${BUILD_DATE}"
echo "Commit: ${GITHUB_SHA}"
echo ""

docker buildx build \
    --platform linux/amd64 \
    --file docker/Dockerfile \
    --tag "${IMAGE_NAME}:${TAG}" \
    --build-arg BUILD_DATE="${BUILD_DATE}" \
    --build-arg GITHUB_SHA="${GITHUB_SHA}" \
    --build-arg BUILD_VERSION="${TAG}" \
    --push \
    .

echo ""
echo "Build and push complete: ${IMAGE_NAME}:${TAG}"
