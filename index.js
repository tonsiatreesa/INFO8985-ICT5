
// OpenTelemetry comprehensive instrumentation for browser - Simplified approach
import { WebTracerProvider } from 'https://cdn.jsdelivr.net/npm/@opentelemetry/sdk-trace-web@1.15.2/+esm';
import { OTLPTraceExporter } from 'https://cdn.jsdelivr.net/npm/@opentelemetry/exporter-trace-otlp-http@0.41.2/+esm';
import { BatchSpanProcessor } from 'https://cdn.jsdelivr.net/npm/@opentelemetry/sdk-trace-base@1.15.2/+esm';
import { trace } from 'https://cdn.jsdelivr.net/npm/@opentelemetry/api@1.4.1/+esm';
import { loadScript } from 'https://cdn.jsdelivr.net/npm/@paypal/paypal-js@8.1.2/+esm';

// OTel Configuration - Using local proxy to avoid CORS issues
const otlpBaseEndpoint = 'http://localhost:8000/proxy'; // Use local proxy
const otlpTraceEndpoint = `${otlpBaseEndpoint}/v1/traces`;

// Simple resource configuration (inline to avoid import issues)
const serviceResource = {
  'service.name': 'paypal-frontend',
  'service.version': '1.0.0',
  'deployment.environment': 'development'
};

// Enhanced trace provider setup with batching
const traceExporter = new OTLPTraceExporter({ 
  url: otlpTraceEndpoint,
  headers: {
    'Content-Type': 'application/json'
  }
});

const traceProvider = new WebTracerProvider({
  resource: {
    attributes: serviceResource
  }
});

traceProvider.addSpanProcessor(new BatchSpanProcessor(traceExporter, {
  maxQueueSize: 100,
  maxExportBatchSize: 10,
  scheduledDelayMillis: 500,
  exportTimeoutMillis: 30000
}));

traceProvider.register();
const tracer = trace.getTracer('paypal-frontend', '1.0.0');

// Simple metrics (using basic counters without complex imports)
let actionCount = 0;
let errorCount = 0;

// Custom logging function with OTel correlation
function logWithTrace(level, message, attributes = {}) {
  const span = trace.getActiveSpan();
  const traceId = span?.spanContext()?.traceId || 'no-trace';
  const spanId = span?.spanContext()?.spanId || 'no-span';
  
  console[level](`[${traceId}:${spanId}] ${message}`, attributes);
  
  // Send simple telemetry data
  if (level === 'error') {
    errorCount++;
  }
  actionCount++;
}

// Error handling function
function handleError(error, span, operation, additionalAttributes = {}) {
  if (span) {
    span.recordException(error);
    span.setStatus({ code: 2, message: error.message }); // ERROR status
    span.setAttributes({
      'error.type': error.constructor.name,
      'error.message': error.message,
      'error.stack': error.stack,
      ...additionalAttributes
    });
  }
  
  errorCount++;
  logWithTrace('error', `Error in ${operation}: ${error.message}`, { error, ...additionalAttributes });
}

// Page load instrumentation
const pageLoadSpan = tracer.startSpan('page_load');
pageLoadSpan.setAttributes({
  'page.url': window.location.href,
  'page.title': document.title,
  'user.agent': navigator.userAgent
});

actionCount++;

// Close page load span when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  pageLoadSpan.setAttributes({
    'page.load_state': 'dom_ready'
  });
  pageLoadSpan.end();
  logWithTrace('info', 'Page DOM ready');
});

// TEST: Emit initial telemetry to verify OTel export
const testSpan = tracer.startSpan('otel_test_span');
testSpan.setAttributes({
  'test.type': 'connectivity',
  'test.timestamp': new Date().toISOString()
});
testSpan.end();

logWithTrace('info', 'OpenTelemetry initialized successfully');

class Year extends HTMLElement {
    connectedCallback() {
        this.innerHTML = new Date().getFullYear();
    }
}

customElements.define("x-date", Year);

class PayPal extends HTMLElement {
    static observedAttributes = ["amount"];

    constructor() {
        super();
        this.startTime = performance.now();
    }

    async connectedCallback() {
        const componentSpan = tracer.startSpan('paypal_component_connect');
        
        try {
            componentSpan.setAttributes({
                'component.type': 'paypal-button',
                'component.amount': this.getAttribute('amount') || '100'
            });

            logWithTrace('info', 'PayPal component connecting');

            // Always clear the PayPal button container before rendering
            this.innerHTML = `
                <div id="paypal-button-container"></div>
                <p id="result-message"></p>
            `;

            // Fetch client ID with instrumentation
            const clientIdSpan = tracer.startSpan('fetch_client_id');
            let oClient;
            
            try {
                clientIdSpan.setAttributes({
                    'http.method': 'GET',
                    'http.url': import.meta.url.replace("index.js", "clientid")
                });
                
                const res = await fetch(import.meta.url.replace("index.js", "clientid"));
                
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
                }
                
                oClient = await res.json();
                
                clientIdSpan.setAttributes({
                    'http.status_code': res.status,
                    'client.id_configured': !!oClient?.clientid && oClient.clientid !== 'not_set'
                });
                
                logWithTrace('info', 'Client ID fetched successfully', { clientIdConfigured: !!oClient?.clientid });
                
            } catch (error) {
                handleError(error, clientIdSpan, 'fetch_client_id');
                throw error;
            } finally {
                clientIdSpan.end();
            }

            let paypal;
            
            // PayPal SDK loading with enhanced instrumentation
            const loadSpan = tracer.startSpan('paypal_sdk_load');
            const loadStartTime = performance.now();
            
            try {
                loadSpan.setAttributes({
                    'sdk.client_id': oClient.clientid,
                    'sdk.version': '8.1.2'
                });

                if (window.paypal) {
                    paypal = window.paypal;
                    loadSpan.setAttributes({
                        'sdk.load_method': 'already_loaded',
                        'sdk.cached': true
                    });
                    logWithTrace('info', 'PayPal SDK already loaded');
                } else {
                    paypal = await loadScript({ clientId: oClient.clientid });
                    loadSpan.setAttributes({
                        'sdk.load_method': 'fresh_load',
                        'sdk.cached': false
                    });
                    logWithTrace('info', 'PayPal SDK loaded fresh');
                }

                const loadDuration = (performance.now() - loadStartTime) / 1000;
                // Simple duration tracking without complex metrics
                console.log(`PayPal SDK load duration: ${loadDuration}s`);

                actionCount++;

                paypal.resultMessage = (sMessage) => {
                    document.querySelector("#result-message").innerHTML = sMessage;
                    logWithTrace('info', 'PayPal result message updated', { message: sMessage });
                };

            } catch (error) {
                handleError(error, loadSpan, 'paypal_sdk_load', {
                    'sdk.client_id': oClient?.clientid || 'unknown'
                });
                actionCount++;
                throw error;
            } finally {
                loadSpan.end();
            }

            if (paypal) {
                await this.renderPayPalButtons(paypal, componentSpan);
            }

            const totalDuration = (performance.now() - this.startTime) / 1000;
            console.log(`PayPal component total init duration: ${totalDuration}s`);

            componentSpan.setAttributes({
                'component.initialized': true,
                'component.duration_seconds': totalDuration
            });

            logWithTrace('info', 'PayPal component initialized successfully');

        } catch (error) {
            handleError(error, componentSpan, 'paypal_component_connect');
            const totalDuration = (performance.now() - this.startTime) / 1000;
            console.log(`PayPal component init failed after: ${totalDuration}s`);
        } finally {
            componentSpan.end();
        }
    }

    async renderPayPalButtons(paypal, parentSpan) {
        const renderSpan = tracer.startSpan('paypal_button_render', { parent: parentSpan });
        const renderStartTime = performance.now();

        try {
            renderSpan.setAttributes({
                'button.style': 'rect',
                'button.layout': 'vertical',
                'button.color': 'gold'
            });

            // Always clear the container before rendering
            const container = this.querySelector('#paypal-button-container');
            if (container) container.innerHTML = '';

            await paypal.Buttons({
                style: {
                    shape: "rect",
                    layout: "vertical", 
                    color: "gold",
                    label: "paypal",
                },
                createOrder: async () => {
                    return await this.createOrderWithInstrumentation();
                },
                onApprove: async (data, actions) => {
                    return await this.onApproveWithInstrumentation(data, actions, paypal);
                },
                onError: (err) => {
                    this.onErrorWithInstrumentation(err, paypal);
                },
                onCancel: (data) => {
                    this.onCancelWithInstrumentation(data, paypal);
                }
            }).render("#paypal-button-container");

            const renderDuration = (performance.now() - renderStartTime) / 1000;
            console.log(`PayPal buttons render duration: ${renderDuration}s`);

            actionCount++;

            renderSpan.setAttributes({
                'button.rendered': true,
                'button.duration_seconds': renderDuration
            });

            logWithTrace('info', 'PayPal buttons rendered successfully');

        } catch (error) {
            handleError(error, renderSpan, 'paypal_button_render');
            const renderDuration = (performance.now() - renderStartTime) / 1000;
            console.log(`PayPal buttons render failed after: ${renderDuration}s`);
            errorCount++;
        } finally {
            renderSpan.end();
        }
    }

    async createOrderWithInstrumentation() {
        const createOrderSpan = tracer.startSpan('paypal_create_order');
        const startTime = performance.now();

        try {
            createOrderSpan.setAttributes({
                'order.amount': this.getAttribute('amount') || '100',
                'order.currency': 'USD',
                'http.method': 'POST',
                'http.url': import.meta.url.replace("index.js", "orders")
            });

            logWithTrace('info', 'Creating PayPal order');

            const response = await fetch(import.meta.url.replace("index.js", "orders"), {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    cart: [
                        {
                            id: "YOUR_PRODUCT_ID",
                            quantity: "YOUR_PRODUCT_QUANTITY",
                        },
                    ],
                }),
            });

            createOrderSpan.setAttributes({
                'http.status_code': response.status,
                'http.status_text': response.statusText
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const orderData = await response.json();

            if (orderData.id) {
                createOrderSpan.setAttributes({
                    'order.id': orderData.id,
                    'order.status': 'created'
                });

                const duration = (performance.now() - startTime) / 1000;
                console.log(`Order creation duration: ${duration}s`);

                actionCount++;

                logWithTrace('info', 'PayPal order created successfully', { orderId: orderData.id });
                return orderData.id;
            }

            const errorDetail = orderData?.details?.[0];
            const errorMessage = errorDetail
                ? `${errorDetail.issue} ${errorDetail.description} (${orderData.debug_id})`
                : JSON.stringify(orderData);
            
            throw new Error(errorMessage);

        } catch (error) {
            handleError(error, createOrderSpan, 'paypal_create_order');
            
            const duration = (performance.now() - startTime) / 1000;
            console.log(`Order creation failed after: ${duration}s`);

            errorCount++;

            if (window.paypal?.resultMessage) {
                window.paypal.resultMessage(`Could not initiate PayPal Checkout...<br><br>${error}`);
            }
            throw error;
        } finally {
            createOrderSpan.end();
        }
    }

    async onApproveWithInstrumentation(data, actions, paypal) {
        const approveSpan = tracer.startSpan('paypal_on_approve');
        const startTime = performance.now();

        try {
            approveSpan.setAttributes({
                'order.id': data.orderID,
                'payment.id': data.paymentID || 'unknown',
                'payer.id': data.payerID || 'unknown',
                'http.method': 'POST',
                'http.url': import.meta.url.replace("index.js", `capture/${data.orderID}`)
            });

            logWithTrace('info', 'PayPal payment approved, capturing order', { orderId: data.orderID });

            const response = await fetch(
                import.meta.url.replace("index.js", `capture/${data.orderID}`),
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                }
            );

            approveSpan.setAttributes({
                'http.status_code': response.status,
                'http.status_text': response.statusText
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const orderData = await response.json();
            const errorDetail = orderData?.details?.[0];

            if (errorDetail?.issue === "INSTRUMENT_DECLINED") {
                approveSpan.setAttributes({
                    'payment.status': 'instrument_declined',
                    'payment.restart': true
                });

                actionCount++;

                logWithTrace('warn', 'Payment instrument declined, restarting');
                return actions.restart();
            } else if (errorDetail) {
                throw new Error(`${errorDetail.description} (${orderData.debug_id})`);
            } else if (!orderData.purchase_units) {
                throw new Error(JSON.stringify(orderData));
            } else {
                const transaction = orderData?.purchase_units?.[0]?.payments?.captures?.[0] 
                    || orderData?.purchase_units?.[0]?.payments?.authorizations?.[0];

                approveSpan.setAttributes({
                    'payment.status': 'completed',
                    'transaction.id': transaction?.id || 'unknown',
                    'transaction.status': transaction?.status || 'unknown',
                    'transaction.amount': transaction?.amount?.value || '0',
                    'transaction.currency': transaction?.amount?.currency_code || 'USD'
                });

                const duration = (performance.now() - startTime) / 1000;
                console.log(`Payment approval duration: ${duration}s`);

                actionCount++;

                logWithTrace('info', 'Payment completed successfully', {
                    transactionId: transaction?.id,
                    status: transaction?.status
                });

                paypal.resultMessage(
                    `Transaction ${transaction.status}: ${transaction.id}<br>
                    <br>See console for all available details`
                );
                console.log("Capture result", orderData, JSON.stringify(orderData, null, 2));
            }

        } catch (error) {
            handleError(error, approveSpan, 'paypal_on_approve', {
                'order.id': data.orderID
            });

            const duration = (performance.now() - startTime) / 1000;
            console.log(`Payment approval failed after: ${duration}s`);

            errorCount++;

            paypal.resultMessage(
                `Sorry, your transaction could not be processed...<br><br>${error}`
            );
        } finally {
            approveSpan.end();
        }
    }

    onErrorWithInstrumentation(err, paypal) {
        const errorSpan = tracer.startSpan('paypal_on_error');
        
        try {
            handleError(err, errorSpan, 'paypal_on_error');
            
            errorCount++;

            paypal.resultMessage(`PayPal error occurred: ${err}`);
            logWithTrace('error', 'PayPal button error occurred', { error: err });

        } finally {
            errorSpan.end();
        }
    }

    onCancelWithInstrumentation(data, paypal) {
        const cancelSpan = tracer.startSpan('paypal_on_cancel');
        
        try {
            cancelSpan.setAttributes({
                'payment.status': 'cancelled',
                'order.id': data.orderID || 'unknown'
            });

            actionCount++;

            paypal.resultMessage("Payment was cancelled by the user.");
            logWithTrace('info', 'Payment cancelled by user', { orderId: data.orderID });

        } finally {
            cancelSpan.end();
        }
    }
}

customElements.define("x-paypal", PayPal)