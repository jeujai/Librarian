#!/bin/bash
"""
Install Scheduled Cleanup Service

This script installs the scheduled cleanup service as a systemd service
for automatic resource management.
"""

set -e

# Configuration
SERVICE_NAME="multimodal-librarian-cleanup"
SERVICE_USER="${USER}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_PATH="$(which python3)"
CONFIG_FILE="${PROJECT_ROOT}/config/cleanup-config.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    print_status "Checking requirements..."
    
    # Check if running as root for system service installation
    if [[ $EUID -eq 0 ]]; then
        print_error "Do not run this script as root. It will use sudo when needed."
        exit 1
    fi
    
    # Check if systemd is available
    if ! command -v systemctl &> /dev/null; then
        print_error "systemctl not found. This script requires systemd."
        exit 1
    fi
    
    # Check if Python 3 is available
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found. Please install Python 3."
        exit 1
    fi
    
    # Check if project files exist
    if [[ ! -f "${PROJECT_ROOT}/scripts/scheduled-cleanup.py" ]]; then
        print_error "Scheduled cleanup script not found at ${PROJECT_ROOT}/scripts/scheduled-cleanup.py"
        exit 1
    fi
    
    if [[ ! -f "${CONFIG_FILE}" ]]; then
        print_error "Configuration file not found at ${CONFIG_FILE}"
        exit 1
    fi
    
    print_success "Requirements check passed"
}

install_python_dependencies() {
    print_status "Installing Python dependencies..."
    
    # Check if schedule module is available
    if ! python3 -c "import schedule" &> /dev/null; then
        print_warning "Installing required Python package: schedule"
        pip3 install --user schedule
    fi
    
    print_success "Python dependencies installed"
}

create_systemd_service() {
    print_status "Creating systemd service file..."
    
    # Create the service file content
    cat > "/tmp/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Multimodal Librarian Scheduled Cleanup Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${PROJECT_ROOT}
Environment=PATH=${PATH}
Environment=PYTHONPATH=${PROJECT_ROOT}/src
ExecStart=${PYTHON_PATH} ${PROJECT_ROOT}/scripts/scheduled-cleanup.py --config ${CONFIG_FILE} --daemon
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${PROJECT_ROOT}
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

[Install]
WantedBy=multi-user.target
EOF

    # Install the service file
    sudo mv "/tmp/${SERVICE_NAME}.service" "/etc/systemd/system/"
    sudo chown root:root "/etc/systemd/system/${SERVICE_NAME}.service"
    sudo chmod 644 "/etc/systemd/system/${SERVICE_NAME}.service"
    
    print_success "Systemd service file created"
}

enable_and_start_service() {
    print_status "Enabling and starting the service..."
    
    # Reload systemd daemon
    sudo systemctl daemon-reload
    
    # Enable the service to start on boot
    sudo systemctl enable "${SERVICE_NAME}"
    
    # Start the service
    sudo systemctl start "${SERVICE_NAME}"
    
    print_success "Service enabled and started"
}

verify_installation() {
    print_status "Verifying installation..."
    
    # Check service status
    if sudo systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_success "Service is running"
    else
        print_error "Service is not running"
        print_status "Service status:"
        sudo systemctl status "${SERVICE_NAME}" --no-pager
        return 1
    fi
    
    # Check if service is enabled
    if sudo systemctl is-enabled --quiet "${SERVICE_NAME}"; then
        print_success "Service is enabled for startup"
    else
        print_warning "Service is not enabled for startup"
    fi
    
    print_success "Installation verification completed"
}

show_usage_info() {
    print_status "Installation completed successfully!"
    echo ""
    echo "Service Management Commands:"
    echo "  sudo systemctl status ${SERVICE_NAME}     # Check service status"
    echo "  sudo systemctl stop ${SERVICE_NAME}       # Stop the service"
    echo "  sudo systemctl start ${SERVICE_NAME}      # Start the service"
    echo "  sudo systemctl restart ${SERVICE_NAME}    # Restart the service"
    echo "  sudo systemctl disable ${SERVICE_NAME}    # Disable auto-start"
    echo ""
    echo "Log Management:"
    echo "  sudo journalctl -u ${SERVICE_NAME}        # View service logs"
    echo "  sudo journalctl -u ${SERVICE_NAME} -f     # Follow service logs"
    echo "  sudo journalctl -u ${SERVICE_NAME} --since today  # Today's logs"
    echo ""
    echo "Configuration:"
    echo "  Edit: ${CONFIG_FILE}"
    echo "  After editing config, restart service: sudo systemctl restart ${SERVICE_NAME}"
    echo ""
    echo "Manual Testing:"
    echo "  python3 ${PROJECT_ROOT}/scripts/scheduled-cleanup.py --test"
    echo ""
    echo "Uninstall:"
    echo "  ${PROJECT_ROOT}/scripts/uninstall-cleanup-service.sh"
}

uninstall_service() {
    print_status "Uninstalling cleanup service..."
    
    # Stop and disable the service
    if sudo systemctl is-active --quiet "${SERVICE_NAME}"; then
        sudo systemctl stop "${SERVICE_NAME}"
        print_success "Service stopped"
    fi
    
    if sudo systemctl is-enabled --quiet "${SERVICE_NAME}"; then
        sudo systemctl disable "${SERVICE_NAME}"
        print_success "Service disabled"
    fi
    
    # Remove service file
    if [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]; then
        sudo rm "/etc/systemd/system/${SERVICE_NAME}.service"
        print_success "Service file removed"
    fi
    
    # Reload systemd daemon
    sudo systemctl daemon-reload
    
    print_success "Cleanup service uninstalled"
}

main() {
    echo "Multimodal Librarian - Scheduled Cleanup Service Installer"
    echo "=========================================================="
    echo ""
    
    case "${1:-install}" in
        install)
            check_requirements
            install_python_dependencies
            create_systemd_service
            enable_and_start_service
            verify_installation
            show_usage_info
            ;;
        uninstall)
            uninstall_service
            ;;
        status)
            sudo systemctl status "${SERVICE_NAME}" --no-pager
            ;;
        logs)
            sudo journalctl -u "${SERVICE_NAME}" -f
            ;;
        test)
            python3 "${PROJECT_ROOT}/scripts/scheduled-cleanup.py" --test
            ;;
        *)
            echo "Usage: $0 [install|uninstall|status|logs|test]"
            echo ""
            echo "Commands:"
            echo "  install   - Install and start the cleanup service (default)"
            echo "  uninstall - Stop and remove the cleanup service"
            echo "  status    - Show service status"
            echo "  logs      - Show and follow service logs"
            echo "  test      - Test the cleanup service"
            exit 1
            ;;
    esac
}

main "$@"