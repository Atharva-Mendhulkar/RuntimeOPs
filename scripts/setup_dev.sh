#!/bin/bash
# IBM Bob - Development Environment Setup Script

set -e

echo "🚀 Setting up IBM Bob development environment..."

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command -v python3.11 &> /dev/null; then
    echo "❌ Python 3.11+ is required but not installed"
    exit 1
fi
echo "✅ Python 3.11+ found"

if ! command -v docker &> /dev/null; then
    echo "❌ Docker is required but not installed"
    exit 1
fi
echo "✅ Docker found"

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is required but not installed"
    exit 1
fi
echo "✅ Docker Compose found"

# Install Poetry if not present
if ! command -v poetry &> /dev/null; then
    echo "📦 Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "✅ Poetry found"
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your API keys"
else
    echo "✅ .env file exists"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
poetry install --no-interaction

# Install pre-commit hooks
echo "🔧 Installing pre-commit hooks..."
poetry run pre-commit install

# Start infrastructure services
echo "🐳 Starting infrastructure services..."
cd docker
docker-compose up -d neo4j weaviate postgres redis

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check service health
echo "🏥 Checking service health..."

# Neo4j
if curl -s http://localhost:7474 > /dev/null; then
    echo "✅ Neo4j is ready"
else
    echo "⚠️  Neo4j may not be ready yet"
fi

# Weaviate
if curl -s http://localhost:8080/v1/.well-known/ready > /dev/null; then
    echo "✅ Weaviate is ready"
else
    echo "⚠️  Weaviate may not be ready yet"
fi

# PostgreSQL
if docker-compose exec -T postgres pg_isready -U bob > /dev/null 2>&1; then
    echo "✅ PostgreSQL is ready"
else
    echo "⚠️  PostgreSQL may not be ready yet"
fi

# Redis
if docker-compose exec -T redis redis-cli -a bobpassword123 ping > /dev/null 2>&1; then
    echo "✅ Redis is ready"
else
    echo "⚠️  Redis may not be ready yet"
fi

cd ..

echo ""
echo "✨ Development environment setup complete!"
echo ""
echo "📚 Next steps:"
echo "  1. Edit .env and add your API keys (OpenAI/Gemini)"
echo "  2. Run 'poetry run uvicorn bob.main:app --reload' to start Bob API"
echo "  3. Visit http://localhost:8000/docs for API documentation"
echo ""
echo "🔗 Service URLs:"
echo "  - Bob API: http://localhost:8000"
echo "  - Neo4j Browser: http://localhost:7474 (neo4j/bobpassword123)"
echo "  - Weaviate: http://localhost:8080"
echo "  - Grafana: http://localhost:3000 (admin/admin)"
echo "  - Jaeger: http://localhost:16686"
echo ""

# Made with Bob
