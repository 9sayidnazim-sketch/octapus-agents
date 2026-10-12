#!/usr/bin/env bash
set -euo pipefail

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO_NAME="${ECR_REPO_NAME:-octapus-staff-assistant}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Octapus Staff Assistant AWS Deployment ==="

# Check AWS CLI authentication
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "❌ Error: AWS CLI is not configured or authenticated."
    echo "👉 Please run 'aws configure' with your AWS Access Key, Secret Key, and Region first."
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
echo "✅ Authenticated to AWS Account: ${ACCOUNT_ID} (Region: ${AWS_REGION})"

# Ensure ECR repository exists
echo "📦 Ensuring ECR repository '${ECR_REPO_NAME}' exists..."
aws ecr describe-repositories --repository-names "${ECR_REPO_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1 || \
aws ecr create-repository --repository-name "${ECR_REPO_NAME}" --region "${AWS_REGION}" >/dev/null

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

# Authenticate Docker to ECR
echo "🔑 Logging in Docker to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Build Docker image
echo "🔨 Building Docker image (linux/amd64 for AWS)..."
docker build --platform linux/amd64 -t "${ECR_REPO_NAME}:${IMAGE_TAG}" "${ROOT_DIR}/staff-assistant"

# Tag and Push Docker image
echo "🚀 Tagging and pushing image to ${ECR_URI}:${IMAGE_TAG}..."
docker tag "${ECR_REPO_NAME}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

echo ""
echo "============================================================"
echo "🎉 Image successfully pushed to ECR: ${ECR_URI}:${IMAGE_TAG}"
echo "============================================================"
echo ""
echo "Next step: Deploy with AWS App Runner or ECS:"
echo ""
echo "Option A (AWS App Runner - Recommended for simplicity & SSL):"
echo "  Open AWS Console -> App Runner -> Create Service -> Container registry"
echo "  Image URI: ${ECR_URI}:${IMAGE_TAG}"
echo "  Port: 8001"
echo ""
echo "Option B (AWS CLI App Runner create service):"
echo "  aws apprunner create-service \\"
echo "    --service-name octapus-staff-assistant \\"
echo "    --source-configuration ImageRepository={ImageIdentifier=${ECR_URI}:${IMAGE_TAG},ImageRepositoryType=ECR,ImageConfiguration={Port=8001}} \\"
echo "    --region ${AWS_REGION}"
echo "============================================================"
