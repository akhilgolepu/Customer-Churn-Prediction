"""
Alert Routing Service - Send drift and performance alerts to various channels.

Supports Slack, Email, PagerDuty, and custom webhooks for alert delivery.
"""

import logging
from typing import Dict, List, Optional, Any
from enum import Enum
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertChannel(ABC):
    """Base class for alert channels."""

    @abstractmethod
    def send(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send alert through this channel.

        Args:
            title: Alert title
            message: Alert message
            severity: Severity level
            details: Additional details dictionary

        Returns:
            True if sent successfully
        """
        pass


class SlackAlertChannel(AlertChannel):
    """Send alerts to Slack."""

    def __init__(self, webhook_url: str, channel: Optional[str] = None):
        """
        Initialize Slack channel.

        Args:
            webhook_url: Slack incoming webhook URL
            channel: Slack channel override (optional)
        """
        self.webhook_url = webhook_url
        self.channel = channel

    def send(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send alert to Slack."""
        try:
            import requests

            # Color coding by severity
            color_map = {
                AlertSeverity.CRITICAL: "#FF0000",
                AlertSeverity.HIGH: "#FF9900",
                AlertSeverity.MEDIUM: "#FFFF00",
                AlertSeverity.LOW: "#0099FF",
                AlertSeverity.INFO: "#00CC00",
            }

            payload = {
                "attachments": [
                    {
                        "fallback": f"{severity.value}: {title}",
                        "color": color_map.get(severity, "#808080"),
                        "title": title,
                        "text": message,
                        "ts": int(datetime.utcnow().timestamp()),
                    }
                ]
            }

            if details:
                fields = [
                    {
                        "title": k,
                        "value": str(v),
                        "short": len(str(v)) < 50,
                    }
                    for k, v in details.items()
                ]
                payload["attachments"][0]["fields"] = fields

            if self.channel:
                payload["channel"] = self.channel

            response = requests.post(self.webhook_url, json=payload)
            if response.status_code == 200:
                logger.info(f"Slack alert sent: {title}")
                return True
            else:
                logger.error(f"Slack alert failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error sending Slack alert: {e}")
            return False


class EmailAlertChannel(AlertChannel):
    """Send alerts via email."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender_email: str,
        sender_password: str,
        recipients: List[str],
    ):
        """
        Initialize email channel.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            sender_email: Sender email address
            sender_password: Sender email password
            recipients: List of recipient emails
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.recipients = recipients

    def send(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send alert via email."""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{severity.value.upper()}] {title}"
            msg["From"] = self.sender_email
            msg["To"] = ", ".join(self.recipients)

            # Build HTML content
            html_parts = [
                f"<h2>{title}</h2>",
                f"<p><strong>Severity:</strong> {severity.value}</p>",
                f"<p><strong>Time:</strong> {datetime.utcnow().isoformat()}</p>",
                f"<p>{message}</p>",
            ]

            if details:
                html_parts.append("<h3>Details:</h3>")
                html_parts.append("<ul>")
                for k, v in details.items():
                    html_parts.append(f"<li><strong>{k}:</strong> {v}</li>")
                html_parts.append("</ul>")

            html_content = "\n".join(html_parts)
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, self.recipients, msg.as_string())

            logger.info(f"Email alert sent to {self.recipients}: {title}")
            return True

        except Exception as e:
            logger.error(f"Error sending email alert: {e}")
            return False


class PagerDutyAlertChannel(AlertChannel):
    """Send alerts to PagerDuty."""

    def __init__(self, integration_key: str, service_id: Optional[str] = None):
        """
        Initialize PagerDuty channel.

        Args:
            integration_key: PagerDuty integration key
            service_id: PagerDuty service ID (optional)
        """
        self.integration_key = integration_key
        self.service_id = service_id

    def send(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send alert to PagerDuty."""
        try:
            import requests

            # Map to PagerDuty severity
            severity_map = {
                AlertSeverity.CRITICAL: "critical",
                AlertSeverity.HIGH: "error",
                AlertSeverity.MEDIUM: "warning",
                AlertSeverity.LOW: "info",
                AlertSeverity.INFO: "info",
            }

            payload = {
                "routing_key": self.integration_key,
                "event_action": "trigger",
                "dedup_key": f"{title}_{datetime.utcnow().isoformat()}",
                "payload": {
                    "summary": title,
                    "severity": severity_map.get(severity, "warning"),
                    "source": "churn_predictor",
                    "custom_details": details or {},
                },
            }

            response = requests.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
            )

            if response.status_code == 202:
                logger.info(f"PagerDuty alert sent: {title}")
                return True
            else:
                logger.error(f"PagerDuty alert failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error sending PagerDuty alert: {e}")
            return False


class WebhookAlertChannel(AlertChannel):
    """Send alerts to generic webhook."""

    def __init__(self, webhook_url: str, custom_headers: Optional[Dict[str, str]] = None):
        """
        Initialize webhook channel.

        Args:
            webhook_url: Target webhook URL
            custom_headers: Optional custom HTTP headers
        """
        self.webhook_url = webhook_url
        self.custom_headers = custom_headers or {}

    def send(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send alert via webhook."""
        try:
            import requests

            payload = {
                "title": title,
                "message": message,
                "severity": severity.value,
                "timestamp": datetime.utcnow().isoformat(),
                "details": details or {},
            }

            headers = {
                "Content-Type": "application/json",
                **self.custom_headers,
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=10,
            )

            if response.status_code in [200, 201, 202]:
                logger.info(f"Webhook alert sent: {title}")
                return True
            else:
                logger.error(f"Webhook alert failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error sending webhook alert: {e}")
            return False


class AlertRouter:
    """Route alerts to multiple channels."""

    def __init__(self):
        """Initialize alert router."""
        self.channels: Dict[str, AlertChannel] = {}
        self.severity_rules: Dict[AlertSeverity, List[str]] = {
            AlertSeverity.CRITICAL: [],
            AlertSeverity.HIGH: [],
            AlertSeverity.MEDIUM: [],
            AlertSeverity.LOW: [],
            AlertSeverity.INFO: [],
        }

    def register_channel(self, name: str, channel: AlertChannel):
        """
        Register an alert channel.

        Args:
            name: Channel identifier
            channel: AlertChannel instance
        """
        self.channels[name] = channel
        logger.info(f"Registered alert channel: {name}")

    def set_severity_routing(
        self,
        severity: AlertSeverity,
        channel_names: List[str],
    ):
        """
        Set which channels receive alerts of given severity.

        Args:
            severity: Severity level
            channel_names: List of channel names to route to
        """
        self.severity_rules[severity] = channel_names
        logger.info(f"Set routing for {severity.value}: {channel_names}")

    def send_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.INFO,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, bool]:
        """
        Send alert through configured channels.

        Args:
            title: Alert title
            message: Alert message
            severity: Alert severity
            details: Additional details

        Returns:
            Dict of channel_name -> success
        """
        target_channels = self.severity_rules.get(severity, [])
        results = {}

        for channel_name in target_channels:
            if channel_name not in self.channels:
                logger.warning(f"Channel not registered: {channel_name}")
                results[channel_name] = False
                continue

            channel = self.channels[channel_name]
            try:
                success = channel.send(title, message, severity, details)
                results[channel_name] = success
            except Exception as e:
                logger.error(f"Error routing to {channel_name}: {e}")
                results[channel_name] = False

        return results


def create_router_from_config(config: Dict[str, Any]) -> AlertRouter:
    """
    Create alert router from configuration dict.

    Example config:
    {
        "channels": {
            "slack": {
                "type": "slack",
                "webhook_url": "https://hooks.slack.com/...",
                "channel": "#alerts"
            },
            "email": {
                "type": "email",
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "sender_email": "alerts@example.com",
                "sender_password": "...",
                "recipients": ["team@example.com"]
            }
        },
        "severity_rules": {
            "critical": ["slack", "pagerduty"],
            "high": ["slack", "email"],
            "medium": ["email"],
            "low": ["email"],
            "info": []
        }
    }
    """
    router = AlertRouter()

    # Register channels
    for channel_name, channel_config in config.get("channels", {}).items():
        channel_type = channel_config.get("type")

        try:
            if channel_type == "slack":
                channel = SlackAlertChannel(
                    webhook_url=channel_config["webhook_url"],
                    channel=channel_config.get("channel"),
                )
            elif channel_type == "email":
                channel = EmailAlertChannel(
                    smtp_host=channel_config["smtp_host"],
                    smtp_port=channel_config["smtp_port"],
                    sender_email=channel_config["sender_email"],
                    sender_password=channel_config["sender_password"],
                    recipients=channel_config["recipients"],
                )
            elif channel_type == "pagerduty":
                channel = PagerDutyAlertChannel(
                    integration_key=channel_config["integration_key"],
                    service_id=channel_config.get("service_id"),
                )
            elif channel_type == "webhook":
                channel = WebhookAlertChannel(
                    webhook_url=channel_config["webhook_url"],
                    custom_headers=channel_config.get("headers"),
                )
            else:
                logger.warning(f"Unknown channel type: {channel_type}")
                continue

            router.register_channel(channel_name, channel)

        except Exception as e:
            logger.error(f"Error registering channel {channel_name}: {e}")

    # Set severity rules
    severity_rules = config.get("severity_rules", {})
    for severity_str, channels in severity_rules.items():
        try:
            severity = AlertSeverity[severity_str.upper()]
            router.set_severity_routing(severity, channels)
        except KeyError:
            logger.warning(f"Unknown severity: {severity_str}")

    return router


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: Create router with multiple channels
    config = {
        "channels": {
            "webhook": {
                "type": "webhook",
                "webhook_url": "http://localhost:8000/webhooks/alerts",
            },
        },
        "severity_rules": {
            "critical": ["webhook"],
            "high": ["webhook"],
            "medium": ["webhook"],
            "low": [],
            "info": [],
        },
    }

    router = create_router_from_config(config)

    # Send test alert
    router.send_alert(
        title="Test Alert",
        message="This is a test drift detection alert",
        severity=AlertSeverity.HIGH,
        details={
            "drifted_features": ["feature_1", "feature_2"],
            "severity": "high",
        },
    )
