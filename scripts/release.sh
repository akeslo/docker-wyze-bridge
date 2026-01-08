#!/bin/bash
set -e

# Configuration
IMAGE_NAME="ghcr.io/akeslo/docker-wyze-bridge"
TAG="${1:-latest}"
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
GITHUB_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

# Get version from git tag or use default
if [ "$TAG" = "latest" ]; then
    VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo "dev")
else
    VERSION="$TAG"
fi

echo "════════════════════════════════════════════════════════"
echo "🚀 Docker Wyze Bridge Release"
echo "════════════════════════════════════════════════════════"
echo "Image:      $IMAGE_NAME"
echo "Tag:        $TAG"
echo "Version:    $VERSION"
echo "Build Date: $BUILD_DATE"
echo "Commit:     $GITHUB_SHA"
echo "Platforms:  linux/amd64, linux/arm64, linux/arm/v7"
echo "════════════════════════════════════════════════════════"
echo ""

# Check if we're in the right directory
if [ ! -f "docker/Dockerfile" ]; then
    echo "❌ Error: docker/Dockerfile not found. Run from project root."
    exit 1
fi

# Detect build mode
USE_BUILDX=false
PLATFORMS="linux/amd64,linux/arm64,linux/arm/v7"

if command -v docker &>/dev/null && docker buildx version &>/dev/null; then
    USE_BUILDX=true
    echo "✅ Using docker buildx for multi-platform builds"

    # Create/use buildx builder
    if ! docker buildx inspect multiarch &>/dev/null; then
        echo "📦 Creating buildx builder 'multiarch'..."
        docker buildx create --name multiarch --use
    else
        docker buildx use multiarch
    fi
else
    echo "⚠️  docker buildx not available - using single-platform build"
    echo "   To enable multi-platform builds:"
    echo "   1. Install Docker Desktop (includes buildx)"
    echo "   2. Or install buildx: https://docs.docker.com/buildx/working-with-buildx/"
    echo ""
    PLATFORMS="linux/$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"
    echo "   Building for: $PLATFORMS"
    echo ""
fi

# Build and Push
echo "🔨 Building Docker image..."

if [ "$USE_BUILDX" = true ]; then
    # Multi-platform build with buildx
    docker buildx build \
      --platform "$PLATFORMS" \
      --build-arg BUILD_DATE="$BUILD_DATE" \
      --build-arg BUILD_VERSION="$VERSION" \
      --build-arg GITHUB_SHA="$GITHUB_SHA" \
      --no-cache \
      --push \
      -t "$IMAGE_NAME:$TAG" \
      -f docker/Dockerfile \
      .
else
    # Single-platform build with legacy builder
    docker build \
      --platform "$PLATFORMS" \
      --build-arg BUILD_DATE="$BUILD_DATE" \
      --build-arg BUILD_VERSION="$VERSION" \
      --build-arg GITHUB_SHA="$GITHUB_SHA" \
      --no-cache \
      -t "$IMAGE_NAME:$TAG" \
      -f docker/Dockerfile \
      .

    # Push separately
    echo "📤 Pushing image..."
    docker push "$IMAGE_NAME:$TAG"
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo "✅ Build and Push Complete!"
echo "════════════════════════════════════════════════════════"
echo "Image pushed to: $IMAGE_NAME:$TAG"
echo ""
echo "To pull: docker pull $IMAGE_NAME:$TAG"
echo "════════════════════════════════════════════════════════"

# Clean up old untagged images
echo ""
echo "🧹 Cleaning up old untagged images..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/imgclean.sh" ]; then
    if command -v gh &>/dev/null; then
        bash "$SCRIPT_DIR/imgclean.sh"
    else
        echo "⚠️  GitHub CLI (gh) not installed - skipping image cleanup"
        echo "   Install with: brew install gh"
    fi
else
    echo "⚠️  imgclean.sh not found - skipping image cleanup"
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo "🎉 Release Complete!"
echo "════════════════════════════════════════════════════════"
