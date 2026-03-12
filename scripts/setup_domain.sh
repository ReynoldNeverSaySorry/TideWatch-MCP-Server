#!/bin/bash
# =============================================================================
# TideWatch MCP Server — Domain Setup Script
# Run on Azure VM with: sudo ./setup_domain.sh
# =============================================================================

set -e

DOMAIN="tidewatch.polly.wang"
REPO_DIR="/home/azureuser/GitHub_Workspace/TideWatch-MCP-Server"
NGINX_CONF="$REPO_DIR/config/nginx_tidewatch.polly.wang.conf"

echo "🌊 Setting up domain: $DOMAIN"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (sudo ./setup_domain.sh)"
    exit 1
fi

# Step 1: Check DNS
echo ""
echo "📡 Step 1: Checking DNS resolution..."
DNS_IP=$(dig +short "$DOMAIN" 2>/dev/null || echo "")
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "unknown")

if [ -z "$DNS_IP" ]; then
    echo "⚠️  WARNING: DNS record for $DOMAIN not found!"
    echo ""
    echo "   Please add an A record in Cloudflare:"
    echo "   ┌────────────────────────────────────────┐"
    echo "   │ Type: A                                │"
    echo "   │ Name: tidewatch                        │"
    echo "   │ Value: $SERVER_IP                      │"
    echo "   │ Proxy: DNS only (grey cloud)           │"
    echo "   └────────────────────────────────────────┘"
    echo ""
    read -p "Press Enter after adding DNS record, or Ctrl+C to cancel..."
elif [ "$DNS_IP" != "$SERVER_IP" ]; then
    echo "⚠️  WARNING: DNS points to $DNS_IP but server IP is $SERVER_IP"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ DNS correctly points to $SERVER_IP"
fi

# Step 2: Install Nginx config
echo ""
echo "📝 Step 2: Installing Nginx configuration..."
cp "$NGINX_CONF" "/etc/nginx/sites-available/$DOMAIN"
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
echo "✅ Nginx configuration installed"

# Step 3: Test Nginx
echo ""
echo "🔍 Step 3: Testing Nginx configuration..."
nginx -t
echo "✅ Nginx configuration is valid"

# Step 4: Reload Nginx
echo ""
echo "🔄 Step 4: Reloading Nginx..."
systemctl reload nginx
echo "✅ Nginx reloaded"

# Step 5: SSL
echo ""
echo "🔒 Step 5: Setting up SSL certificate with Let's Encrypt..."
read -p "Install SSL certificate now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@polly.wang || {
        echo "⚠️  Certbot failed. Run manually:"
        echo "   sudo certbot --nginx -d $DOMAIN"
    }
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "   Your MCP Server should be accessible at:"
echo "   ┌──────────────────────────────────────────────────┐"
echo "   │ https://$DOMAIN/mcp    (MCP endpoint)     │"
echo "   │ https://$DOMAIN/health (health check)     │"
echo "   └──────────────────────────────────────────────────┘"
echo ""
echo "   Make sure your MCP server is running:"
echo "   cd $REPO_DIR"
echo "   source venv/bin/activate"
echo "   python -m tidewatch.server --http --port 8889"
