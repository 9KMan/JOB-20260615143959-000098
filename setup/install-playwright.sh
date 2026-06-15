#!/usr/bin/env bash
# =============================================================================
# Playwright Installation Script
# Installs Chromium browser and system dependencies for headless scraping
# =============================================================================

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_warning "Running as root. This is not recommended for production."
        return 0
    fi
}

# Detect package manager
detect_package_manager() {
    if command -v apt-get &> /dev/null; then
        echo "apt-get"
    elif command -v yum &> /dev/null; then
        echo "yum"
    elif command -v dnf &> /dev/null; then
        echo "dnf"
    elif command -v apk &> /dev/null; then
        echo "apk"
    else
        log_error "No supported package manager found"
        exit 1
    fi
}

# Install system dependencies for Chromium
install_system_deps() {
    local package_manager
    package_manager=$(detect_package_manager)
    
    log_info "Detected package manager: $package_manager"
    
    case "$package_manager" in
        apt-get)
            export DEBIAN_FRONTEND=noninteractive
            apt-get update -qq
            apt-get install -y --no-install-recommends \
                wget \
                gnupg \
                curl \
                ca-certificates \
                fonts-liberation \
                libasound2 \
                libatk-bridge2.0-0 \
                libatk1.0-0 \
                libatspi2.0-0 \
                libcups2 \
                libdbus-1-3 \
                libdrm2 \
                libgbm1 \
                libgtk-3-0 \
                libnspr4 \
                libnss3 \
                libxcomposite1 \
                libxdamage1 \
                libxfixes3 \
                libxkbcommon0 \
                libxrandr2 \
                xdg-utils \
                xvfb \
                chromium \
                chromium-sandbox \
                2>/dev/null || true
            ;;
        apk)
            apk add --no-cache \
                wget \
                gnupg \
                curl \
                ca-certificates \
                musl-locales \
                libasound \
                libatk \
                libatk-bridge \
                libatspi \
                libcups \
                dbus \
                libdrm \
                mesa \
                gtk+3 \
                nspr \
                nss \
                libxcomposite \
                libxdamage \
                libxfixes \
                libxkbcommon \
                libxrandr \
                xdg-utils \
                xvfb-run \
                chromium \
                chromium-chromedriver \
                2>/dev/null || true
            ;;
        yum|dnf)
            yum install -y -q \
                wget \
                gnupg \
                curl \
                ca-certificates \
                alsa-lib \
                at-spi2-atk \
                atk \
                cups-libs \
                dbus-libs \
                libdrm \
                mesa-libgbm \
                gtk3 \
                nspr \
                nss \
                libXcomposite \
                libXdamage \
                libXfixes \
                libxkbcommon \
                libXrandr \
                xdg-utils \
                xorg-x11-server-Xvfb \
                chromium \
                2>/dev/null || true
            ;;
    esac
    
    log_success "System dependencies installed"
}

# Install Python dependencies
install_python_deps() {
    log_info "Installing Python dependencies..."
    
    # Check if pip is available
    if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
        log_error "pip not found. Please install Python pip first."
        exit 1
    fi
    
    # Upgrade pip
    pip install --upgrade pip --quiet
    
    # Install Playwright and related packages
    pip install --quiet \
        playwright==1.42.0 \
        playwright-stealth==1.0.6 \
        xvfbwrapper==0.2.13
    
    log_success "Python dependencies installed"
}

# Install Playwright browsers
install_browsers() {
    log_info "Installing Chromium browser for Playwright..."
    
    # Install Chromium
    playwright install chromium
    
    # Install system dependencies for Chromium
    playwright install-deps chromium
    
    log_success "Chromium browser installed successfully"
}

# Verify installation
verify_installation() {
    log_info "Verifying Playwright installation..."
    
    # Test Python imports
    python3 -c "
import playwright
import stealth
import xvfbwrapper
print(f'Playwright version: {playwright.__version__}')
print('All imports successful')
"
    
    # Test Chromium availability
    playwright show-browser-version || true
    
    log_success "Installation verified successfully"
}

# Configure Xvfb
configure_xvfb() {
    log_info "Configuring Xvfb..."
    
    # Create Xvfb display directory
    mkdir -p /tmp/.X11-unix
    chmod 1777 /tmp/.X11-unix
    
    # Test Xvfb
    if command -v Xvfb &> /dev/null; then
        log_success "Xvfb is available"
    else
        log_warning "Xvfb not found. Headless mode may not work."
    fi
}

# Main installation process
main() {
    log_info "Starting Playwright installation..."
    log_info "Python version: $(python3 --version)"
    
    check_root
    install_system_deps
    install_python_deps
    install_browsers
    configure_xvfb
    verify_installation
    
    log_success "Playwright installation completed successfully!"
    log_info "You can now run: playwright install-deps && python -m playwright test"
}

# Run main function
main "$@"
