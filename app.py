
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import logging
import time
from typing import Dict, Any
import httpx

# OpenTelemetry imports - comprehensive setup
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry import trace, metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
import logging as py_logging

from paypalserversdk.http.auth.o_auth_2 import ClientCredentialsAuthCredentials

from paypalserversdk.logging.configuration.api_logging_configuration import (

    LoggingConfiguration,

    RequestLoggingConfiguration,

    ResponseLoggingConfiguration,

)

from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient

from paypalserversdk.controllers.orders_controller import OrdersController

from paypalserversdk.controllers.payments_controller import PaymentsController

from paypalserversdk.models.amount_with_breakdown import AmountWithBreakdown

from paypalserversdk.models.checkout_payment_intent import CheckoutPaymentIntent

from paypalserversdk.models.order_request import OrderRequest

from paypalserversdk.models.capture_request import CaptureRequest

from paypalserversdk.models.money import Money

from paypalserversdk.models.shipping_details import ShippingDetails

from paypalserversdk.models.shipping_option import ShippingOption

from paypalserversdk.models.shipping_type import ShippingType

from paypalserversdk.models.purchase_unit_request import PurchaseUnitRequest

from paypalserversdk.models.payment_source import PaymentSource

from paypalserversdk.models.card_request import CardRequest

from paypalserversdk.models.card_attributes import CardAttributes

from paypalserversdk.models.card_verification import CardVerification

from paypalserversdk.api_helper import ApiHelper




load_dotenv()
app = FastAPI()

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OTel: Enhanced setup for tracing, metrics, and logging
# Default to TrueNAS collector endpoint - update for your Cloudflare tunnel
otel_base = os.getenv("OTEL_ENDPOINT", "https://otel.nidhun.me")  # Your Cloudflare tunnel endpoint
otel_traces = otel_base.rstrip("/") + "/v1/traces"
otel_metrics = otel_base.rstrip("/") + "/v1/metrics"
otel_logs = otel_base.rstrip("/") + "/v1/logs"

# Enhanced resource with service metadata
resource = Resource(attributes={
    "service.name": "paypal-backend",
    "service.version": "1.0.0",
    "service.instance.id": os.getenv("HOSTNAME", "localhost"),
    "deployment.environment": os.getenv("ENVIRONMENT", "development")
})

# Configure propagators for distributed tracing
set_global_textmap(B3MultiFormat())

# Tracing setup with enhanced configuration
trace_provider = TracerProvider(resource=resource)
span_processor = BatchSpanProcessor(
    OTLPSpanExporter(endpoint=otel_traces),
    max_queue_size=2048,
    max_export_batch_size=512,
    export_timeout_millis=30000
)
trace_provider.add_span_processor(span_processor)
trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer(__name__)

# Metrics setup with comprehensive configuration
metric_exporter = OTLPMetricExporter(endpoint=otel_metrics)
metric_reader = PeriodicExportingMetricReader(
    metric_exporter, 
    export_interval_millis=10000
)
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter(__name__)

# Custom metrics
request_counter = meter.create_counter(
    "paypal_requests_total",
    description="Total number of PayPal API requests"
)
request_duration = meter.create_histogram(
    "paypal_request_duration_seconds",
    description="Duration of PayPal API requests in seconds"
)
order_counter = meter.create_counter(
    "paypal_orders_total",
    description="Total number of PayPal orders created"
)
error_counter = meter.create_counter(
    "paypal_errors_total",
    description="Total number of PayPal errors"
)

# Logging setup with comprehensive configuration
otel_logger_provider = LoggerProvider(resource=resource)
otel_log_exporter = OTLPLogExporter(endpoint=otel_logs)
otel_logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(otel_log_exporter)
)
otel_handler = LoggingHandler(level=py_logging.INFO, logger_provider=otel_logger_provider)

# Configure logging with both console and OTel handlers
logging_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
console_handler = py_logging.StreamHandler()
console_handler.setFormatter(py_logging.Formatter(logging_format))

py_logging.basicConfig(
    level=py_logging.INFO, 
    handlers=[console_handler, otel_handler],
    format=logging_format
)

logger = py_logging.getLogger(__name__)

# Instrument FastAPI and other libraries
FastAPIInstrumentor.instrument_app(app, tracer_provider=trace_provider)
RequestsInstrumentor().instrument()
LoggingInstrumentor().instrument(set_logging_format=True)


@app.get("/clientid")
async def clientid():
    start_time = time.time()
    with tracer.start_as_current_span("get_clientid") as span:
        try:
            # Add span attributes
            span.set_attribute("endpoint", "/clientid")
            span.set_attribute("method", "GET")
            
            # Count the request
            request_counter.add(1, {"endpoint": "/clientid", "method": "GET"})
            
            logger.info("Fetching PayPal client ID")
            
            client_id = os.environ.get('PAYPAL_CLIENT_ID', 'not_set')
            
            # Set success attributes
            span.set_attribute("success", True)
            span.set_attribute("client_id_configured", client_id != 'not_set')
            
            # Record duration metric
            duration = time.time() - start_time
            request_duration.record(duration, {"endpoint": "/clientid", "method": "GET", "status": "success"})
            
            logger.info(f"Successfully fetched client ID configuration (configured: {client_id != 'not_set'})")
            
            return {"clientid": client_id}
            
        except Exception as e:
            # Record exception in span and metrics
            span.record_exception(e)
            span.set_attribute("success", False)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            
            error_counter.add(1, {"endpoint": "/clientid", "error_type": type(e).__name__})
            
            duration = time.time() - start_time
            request_duration.record(duration, {"endpoint": "/clientid", "method": "GET", "status": "error"})
            
            logger.error(f"Error fetching client ID: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

paypal_client: PaypalServersdkClient = PaypalServersdkClient(

    client_credentials_auth_credentials=ClientCredentialsAuthCredentials(

        o_auth_client_id=os.getenv("PAYPAL_CLIENT_ID"),

        o_auth_client_secret=os.getenv("PAYPAL_CLIENT_SECRET"),

    ),

    logging_configuration=LoggingConfiguration(

        log_level=logging.INFO,

        # Disable masking of sensitive headers for Sandbox testing.

        # This should be set to True (the default if unset)in production.

        mask_sensitive_headers=False,

        request_logging_config=RequestLoggingConfiguration(

            log_headers=True, log_body=True

        ),

        response_logging_config=ResponseLoggingConfiguration(

            log_headers=True, log_body=True

        ),

    ),

)


orders_controller: OrdersController = paypal_client.orders
payments_controller: PaymentsController = paypal_client.payments


@app.post("/orders")
async def create_order(request: Request):
    start_time = time.time()
    with tracer.start_as_current_span("create_order") as span:
        try:
            # Add span attributes
            span.set_attribute("endpoint", "/orders")
            span.set_attribute("method", "POST")
            
            # Count the request
            request_counter.add(1, {"endpoint": "/orders", "method": "POST"})
            
            logger.info("Creating PayPal order")
            
            request_body = await request.json()
            cart = request_body.get("cart", [])
            
            # Add cart details to span
            span.set_attribute("cart.item_count", len(cart))
            span.set_attribute("cart.items", str(cart))
            
            logger.info(f"Processing cart with {len(cart)} items")
            
            # TODO: Calculate amount from cart if needed
            order_amount = "100"  # This should be calculated from cart
            span.set_attribute("order.amount", order_amount)
            span.set_attribute("order.currency", "USD")
            
            order = orders_controller.orders_create({
                "body": OrderRequest(
                    intent=CheckoutPaymentIntent.CAPTURE,
                    purchase_units=[
                        PurchaseUnitRequest(
                            amount=AmountWithBreakdown(
                                currency_code="USD",
                                value=order_amount,
                            ),
                        )
                    ],
                )
            })
            
            # Add order details to span
            order_id = order.body.id if hasattr(order.body, 'id') else 'unknown'
            span.set_attribute("order.id", order_id)
            span.set_attribute("success", True)
            
            # Count successful order creation
            order_counter.add(1, {"status": "created", "amount": order_amount})
            
            # Record duration metric
            duration = time.time() - start_time
            request_duration.record(duration, {"endpoint": "/orders", "method": "POST", "status": "success"})
            
            logger.info(f"Order created successfully: {order_id}")
            
            return order.body
            
        except Exception as e:
            # Record exception in span and metrics
            span.record_exception(e)
            span.set_attribute("success", False)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            
            error_counter.add(1, {"endpoint": "/orders", "error_type": type(e).__name__})
            order_counter.add(1, {"status": "failed"})
            
            duration = time.time() - start_time
            request_duration.record(duration, {"endpoint": "/orders", "method": "POST", "status": "error"})
            
            logger.error(f"Error creating PayPal order: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to create order")


@app.post("/capture/{order_id}")
def capture_order(order_id: str):
    start_time = time.time()
    with tracer.start_as_current_span("capture_order") as span:
        try:
            # Add span attributes
            span.set_attribute("endpoint", "/capture")
            span.set_attribute("method", "POST")
            span.set_attribute("order.id", order_id)
            
            # Count the request
            request_counter.add(1, {"endpoint": "/capture", "method": "POST"})
            
            logger.info(f"Capturing order {order_id}")
            
            order = orders_controller.orders_capture({
                "id": order_id, 
                "prefer": "return=representation"
            })
            
            # Extract capture details for metrics and tracing
            capture_status = "unknown"
            capture_amount = "0"
            transaction_id = "unknown"
            
            if hasattr(order.body, 'purchase_units') and order.body.purchase_units:
                purchase_unit = order.body.purchase_units[0]
                if hasattr(purchase_unit, 'payments') and purchase_unit.payments:
                    if hasattr(purchase_unit.payments, 'captures') and purchase_unit.payments.captures:
                        capture = purchase_unit.payments.captures[0]
                        capture_status = getattr(capture, 'status', 'unknown')
                        transaction_id = getattr(capture, 'id', 'unknown')
                        if hasattr(capture, 'amount'):
                            capture_amount = getattr(capture.amount, 'value', '0')
            
            # Add capture details to span
            span.set_attribute("capture.status", capture_status)
            span.set_attribute("capture.amount", capture_amount)
            span.set_attribute("transaction.id", transaction_id)
            span.set_attribute("success", True)
            
            # Count successful capture
            order_counter.add(1, {"status": "captured", "amount": capture_amount})
            
            # Record duration metric
            duration = time.time() - start_time
            request_duration.record(duration, {"endpoint": "/capture", "method": "POST", "status": "success"})
            
            logger.info(f"Order captured successfully: {order_id}, Transaction: {transaction_id}, Status: {capture_status}")
            
            return order.body
            
        except Exception as e:
            # Record exception in span and metrics
            span.record_exception(e)
            span.set_attribute("success", False)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            
            error_counter.add(1, {"endpoint": "/capture", "error_type": type(e).__name__})
            order_counter.add(1, {"status": "capture_failed"})
            
            duration = time.time() - start_time
            request_duration.record(duration, {"endpoint": "/capture", "method": "POST", "status": "error"})
            
            logger.error(f"Error capturing PayPal order {order_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to capture order")


# Telemetry proxy endpoints to handle CORS issues
@app.post("/proxy/v1/traces")
async def proxy_traces(request: Request):
    """Proxy endpoint for frontend traces to avoid CORS issues"""
    with tracer.start_as_current_span("proxy_traces") as span:
        try:
            span.set_attribute("proxy.type", "traces")
            span.set_attribute("proxy.target", "otel_collector")
            
            # Get the request body
            body = await request.body()
            headers = dict(request.headers)
            
            # Forward to the actual OTel collector
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{otel_base}/v1/traces",
                    content=body,
                    headers={
                        "Content-Type": headers.get("content-type", "application/json"),
                        "Accept": headers.get("accept", "*/*")
                    },
                    timeout=30.0
                )
                
                span.set_attribute("proxy.status_code", response.status_code)
                span.set_attribute("proxy.response_size", len(response.content))
                
                logger.info(f"Proxied traces request: {response.status_code}")
                
                return {
                    "status": "forwarded",
                    "target_status": response.status_code,
                    "message": "Traces forwarded to OTel collector"
                }
                
        except Exception as e:
            span.record_exception(e)
            span.set_attribute("proxy.error", str(e))
            logger.error(f"Error proxying traces: {e}")
            raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")

@app.post("/proxy/v1/metrics")
async def proxy_metrics(request: Request):
    """Proxy endpoint for frontend metrics to avoid CORS issues"""
    with tracer.start_as_current_span("proxy_metrics") as span:
        try:
            span.set_attribute("proxy.type", "metrics")
            span.set_attribute("proxy.target", "otel_collector")
            
            # Get the request body
            body = await request.body()
            headers = dict(request.headers)
            
            # Forward to the actual OTel collector
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{otel_base}/v1/metrics",
                    content=body,
                    headers={
                        "Content-Type": headers.get("content-type", "application/json"),
                        "Accept": headers.get("accept", "*/*")
                    },
                    timeout=30.0
                )
                
                span.set_attribute("proxy.status_code", response.status_code)
                span.set_attribute("proxy.response_size", len(response.content))
                
                logger.info(f"Proxied metrics request: {response.status_code}")
                
                return {
                    "status": "forwarded",
                    "target_status": response.status_code,
                    "message": "Metrics forwarded to OTel collector"
                }
                
        except Exception as e:
            span.record_exception(e)
            span.set_attribute("proxy.error", str(e))
            logger.error(f"Error proxying metrics: {e}")
            raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")

@app.options("/proxy/v1/{path:path}")
async def proxy_options(path: str):
    """Handle OPTIONS requests for CORS preflight"""
    return {"status": "ok"}


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    with tracer.start_as_current_span("health_check") as span:
        span.set_attribute("health.status", "ok")
        logger.info("Health check requested")
        return {
            "status": "healthy",
            "service": "paypal-backend",
            "timestamp": time.time(),
            "otel_endpoint": otel_base
        }




# Serve static files and frontend for the microfrontend PayPal demo app
app.mount('/', StaticFiles(directory=".", html=True), name="src")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
