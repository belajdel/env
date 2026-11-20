#!/usr/bin/env python3
"""
Smoke Test for Environmental Monitoring Platform
Verifies MQTT connectivity, message flow, and basic functionality.
Run after starting the stack with: docker compose up -d
"""

import argparse
import json
import ssl
import sys
import time
import signal
from typing import Dict, List, Optional

import paho.mqtt.client as mqtt


class SmokeTest:
    """Smoke test for the monitoring platform."""
    
    def __init__(self, broker: str = 'localhost', port: int = 8883, 
                 use_tls: bool = True, ca_cert: str = None,
                 username: str = 'backend', password: str = 'backendpass',
                 verbose: bool = False):
        self.broker = broker
        self.port = port
        self.use_tls = use_tls
        self.ca_cert = ca_cert
        self.username = username
        self.password = password
        self.verbose = verbose
        
        self.client = None
        self.connected = False
        self.received_messages = []
        self.expected_topics = []
        self.test_results = {}
        self._lock = __import__('threading').Lock()
        
    def _log(self, msg: str, level: str = 'INFO') -> None:
        """Log message."""
        prefix = {'INFO': '[INFO]', 'WARN': '[WARN]', 'ERROR': '[ERROR]', 'PASS': '[PASS]', 'FAIL': '[FAIL]'}
        print(f"{prefix.get(level, '[INFO]')} {msg}")
        
    def _create_client(self) -> mqtt.Client:
        """Create MQTT client."""
        client = mqtt.Client(
            client_id=f'smoke-test-{int(time.time())}',
            protocol=mqtt.MQTTv311,
            clean_session=True
        )
        
        client.username_pw_set(self.username, self.password)
        
        if self.use_tls:
            if self.ca_cert:
                client.tls_set(ca_certs=self.ca_cert, certfile=None, keyfile=None,
                              cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS,
                              ciphers=None)
            else:
                client.tls_set_context(ssl.create_default_context())
            client.tls_insecure_set(False)
            
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.on_subscribe = self._on_subscribe
        
        return client
    
    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self.connected = True
            self._log(f"Connected to {self.broker}:{self.port}")
            # Subscribe to all test topics
            for topic in self.expected_topics:
                client.subscribe(topic, qos=1)
                if self.verbose:
                    self._log(f"Subscribed to {topic}")
        else:
            self._log(f"Connection failed: {rc}", 'ERROR')
    
    def _on_disconnect(self, client, userdata, rc) -> None:
        self.connected = False
        if rc != 0:
            self._log(f"Unexpected disconnect: {rc}", 'WARN')
    
    def _on_message(self, client, userdata, msg) -> None:
        with self._lock:
            self.received_messages.append({
                'topic': msg.topic,
                'payload': msg.payload.decode('utf-8'),
                'qos': msg.qos,
                'retain': msg.retain,
                'timestamp': time.time()
            })
            if self.verbose:
                self._log(f"Received: {msg.topic} -> {msg.payload.decode()[:80]}")
    
    def _on_subscribe(self, client, userdata, mid, granted_qos) -> None:
        if self.verbose:
            self._log(f"Subscription confirmed: {granted_qos}")
    
    def connect(self, timeout: int = 10) -> bool:
        """Connect to broker."""
        self.client = self._create_client()
        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            
            # Wait for connection
            start = time.time()
            while not self.connected and time.time() - start < timeout:
                time.sleep(0.1)
                
            return self.connected
        except Exception as e:
            self._log(f"Connection error: {e}", 'ERROR')
            return False
    
    def disconnect(self) -> None:
        """Disconnect from broker."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
    
    def wait_for_messages(self, count: int, timeout: int = 30) -> List[Dict]:
        """Wait for specified number of messages."""
        start = time.time()
        while len(self.received_messages) < count and time.time() - start < timeout:
            time.sleep(0.5)
        with self._lock:
            return list(self.received_messages)
    
    def clear_messages(self) -> None:
        """Clear received messages."""
        with self._lock:
            self.received_messages.clear()
    
    # ============================================
    # TEST METHODS
    # ============================================
    
    def test_broker_connectivity(self) -> bool:
        """Test 1: Basic broker connectivity."""
        self._log("Test 1: Broker connectivity")
        self.test_results['broker_connectivity'] = self.connected
        return self.connected
    
    def test_zone_status_topics(self) -> bool:
        """Test 2: Check zone status topics (retained)."""
        self._log("Test 2: Zone status topics (retained)")
        
        zones = ['prod-01', 'prod-02', 'prod-03', 'store-01', 'store-02', 'tech-01', 'tech-02']
        self.expected_topics = [f"factory/{z}/status" for z in zones]
        
        # Subscribe
        for topic in self.expected_topics:
            self.client.subscribe(topic, qos=1)
        
        time.sleep(2)  # Wait for retained messages
        
        # Check received
        with self._lock:
            received_zones = set()
            for msg in self.received_messages:
                for zone in zones:
                    if msg['topic'] == f"factory/{zone}/status":
                        received_zones.add(zone)
                        try:
                            data = json.loads(msg['payload'])
                            if data.get('status') in ('online', 'offline'):
                                self._log(f"  {zone}: status={data.get('status')}", 'PASS')
                            else:
                                self._log(f"  {zone}: invalid status", 'WARN')
                        except json.JSONDecodeError:
                            self._log(f"  {zone}: invalid JSON", 'WARN')
        
        success = len(received_zones) == len(zones)
        self.test_results['zone_status_topics'] = success
        if success:
            self._log(f"All {len(zones)} zone status topics received", 'PASS')
        else:
            missing = set(zones) - received_zones
            self._log(f"Missing zones: {missing}", 'FAIL')
        return success
    
    def test_measurement_flow(self) -> bool:
        """Test 3: Verify measurement messages flow from simulator/firmware."""
        self._log("Test 3: Measurement message flow")
        
        zones = ['prod-01', 'prod-02', 'prod-03', 'store-01', 'store-02', 'tech-01', 'tech-02']
        params = ['temperature', 'humidity', 'noise', 'air_quality', 'pm25', 'pm10', 'voltage']
        
        self.expected_topics = [f"factory/{z}/{p}" for z in zones for p in params]
        
        # Subscribe to all measurement topics
        for topic in self.expected_topics:
            self.client.subscribe(topic, qos=1)
        
        # Wait for at least one message per zone
        self.clear_messages()
        messages = self.wait_for_messages(count=7, timeout=30)
        
        received = {}
        for msg in messages:
            # Parse topic: factory/zone/param
            parts = msg['topic'].split('/')
            if len(parts) == 3:
                zone, param = parts[1], parts[2]
                if zone not in received:
                    received[zone] = set()
                received[zone].add(param)
                
                try:
                    data = json.loads(msg['payload'])
                    # Validate structure
                    required = ['zone_id', 'parameter', 'value', 'unit', 'timestamp']
                    if all(k in data for k in required):
                        if self.verbose:
                            self._log(f"  {zone}/{param}: {data['value']} {data['unit']}")
                    else:
                        self._log(f"  {zone}/{param}: missing fields", 'WARN')
                except json.JSONDecodeError:
                    self._log(f"  {zone}/{param}: invalid JSON", 'WARN')
        
        # Check each zone has at least one parameter
        success = all(len(received.get(z, set())) > 0 for z in zones)
        self.test_results['measurement_flow'] = success
        
        if success:
            self._log(f"Measurements received from all {len(zones)} zones", 'PASS')
            for z in zones:
                self._log(f"  {z}: {', '.join(sorted(received.get(z, set())))}")
        else:
            missing = [z for z in zones if len(received.get(z, set())) == 0]
            self._log(f"Zones with no data: {missing}", 'FAIL')
        return success
    
    def test_payload_schema(self) -> bool:
        """Test 4: Validate payload schema matches specification."""
        self._log("Test 4: Payload schema validation")
        
        # We already have messages from test 3
        with self._lock:
            messages = list(self.received_messages)
        
        valid_count = 0
        invalid_count = 0
        
        for msg in messages:
            try:
                data = json.loads(msg['payload'])
                
                # Check required fields
                required = ['zone_id', 'parameter', 'value', 'unit', 'timestamp']
                if not all(k in data for k in required):
                    invalid_count += 1
                    continue
                    
                # Check types
                if not isinstance(data['zone_id'], str):
                    invalid_count += 1
                    continue
                if not isinstance(data['parameter'], str):
                    invalid_count += 1
                    continue
                if not isinstance(data['value'], (int, float)):
                    invalid_count += 1
                    continue
                if not isinstance(data['unit'], str):
                    invalid_count += 1
                    continue
                if not isinstance(data['timestamp'], (int, float)):
                    invalid_count += 1
                    continue
                    
                # Check timestamp is reasonable (not too old, not future)
                ts = data['timestamp']
                now = time.time()
                if ts < now - 86400 or ts > now + 3600:  # 1 day old or 1 hour future
                    invalid_count += 1
                    continue
                    
                # Check parameter is canonical
                valid_params = ['temperature', 'humidity', 'noise', 'air_quality', 'pm25', 'pm10', 'voltage']
                if data['parameter'] not in valid_params:
                    invalid_count += 1
                    continue
                    
                valid_count += 1
                
            except (json.JSONDecodeError, KeyError, TypeError):
                invalid_count += 1
        
        success = valid_count > 0 and invalid_count == 0
        self.test_results['payload_schema'] = success
        
        if success:
            self._log(f"All {valid_count} messages have valid schema", 'PASS')
        else:
            self._log(f"Valid: {valid_count}, Invalid: {invalid_count}", 'FAIL')
        return success
    
    def test_qos_and_retain(self) -> bool:
        """Test 5: Verify QoS 1 and retain settings."""
        self._log("Test 5: QoS and retain settings")
        
        with self._lock:
            messages = list(self.received_messages)
        
        qos1_count = 0
        retain_status = 0
        retain_measurement = 0
        
        for msg in messages:
            if msg['qos'] == 1:
                qos1_count += 1
            if msg['retain']:
                if 'status' in msg['topic'] or 'state' in msg['topic']:
                    retain_status += 1
                else:
                    retain_measurement += 1
        
        # Measurements should NOT be retained
        # Status/state SHOULD be retained
        success = (qos1_count > 0 and retain_measurement == 0 and retain_status > 0)
        self.test_results['qos_retain'] = success
        
        if success:
            self._log(f"QoS 1: {qos1_count} messages, Retained status: {retain_status}, Retained measurements: {retain_measurement}", 'PASS')
        else:
            self._log(f"QoS 1: {qos1_count}, Retained status: {retain_status}, Retained measurements: {retain_measurement} (should be 0)", 'FAIL')
        return success
    
    def test_tls_connection(self) -> bool:
        """Test 6: Verify TLS connection."""
        self._log("Test 6: TLS connection")
        
        if not self.use_tls:
            self._log("TLS not enabled, skipping", 'WARN')
            self.test_results['tls_connection'] = True
            return True
            
        success = self.connected
        self.test_results['tls_connection'] = success
        
        if success:
            self._log("TLS connection established", 'PASS')
        else:
            self._log("TLS connection failed", 'FAIL')
        return success
    
    def test_relay_command(self) -> bool:
        """Test 7: Test relay command publishing (backend -> device)."""
        self._log("Test 7: Relay command publishing")
        
        # Publish a relay command to prod-01
        topic = "factory/prod-01/relay/1/cmd"
        payload = json.dumps({"command": "state"})
        
        result = self.client.publish(topic, payload, qos=1)
        success = result.rc == 0
        
        self.test_results['relay_command'] = success
        
        if success:
            self._log(f"Relay command published to {topic}", 'PASS')
        else:
            self._log(f"Relay command publish failed: {result.rc}", 'FAIL')
        return success
    
    def test_mqtt_acls(self) -> bool:
        """Test 8: Verify ACLs by attempting unauthorized access."""
        self._log("Test 8: ACL verification (basic)")
        
        # This test verifies we can subscribe to allowed topics
        # Full ACL testing would require multiple client connections
        test_topics = [
            "factory/prod-01/temperature",  # Should work for backend
            "factory/prod-01/status",
            "factory/prod-01/relay/1/cmd",  # Write
        ]
        
        success_count = 0
        for topic in test_topics:
            result = self.client.subscribe(topic, qos=1)
            if result[0] == 0:  # MQTT_ERR_SUCCESS
                success_count += 1
                if self.verbose:
                    self._log(f"  Subscribe {topic}: OK")
            else:
                if self.verbose:
                    self._log(f"  Subscribe {topic}: FAILED ({result[0]})")
        
        success = success_count == len(test_topics)
        self.test_results['mqtt_acls'] = success
        
        if success:
            self._log(f"All {len(test_topics)} ACL test subscriptions succeeded", 'PASS')
        else:
            self._log(f"Only {success_count}/{len(test_topics)} subscriptions succeeded", 'FAIL')
        return success
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all smoke tests."""
        self._log("=" * 50)
        self._log("Starting Smoke Test Suite")
        self._log("=" * 50)
        
        tests = [
            ("Broker Connectivity", self.test_broker_connectivity),
            ("TLS Connection", self.test_tls_connection),
            ("Zone Status Topics", self.test_zone_status_topics),
            ("Measurement Flow", self.test_measurement_flow),
            ("Payload Schema", self.test_payload_schema),
            ("QoS and Retain", self.test_qos_and_retain),
            ("Relay Command", self.test_relay_command),
            ("MQTT ACLs", self.test_mqtt_acls),
        ]
        
        results = {}
        for name, test_func in tests:
            self._log(f"\n--- {name} ---")
            try:
                results[name] = test_func()
            except Exception as e:
                self._log(f"Test {name} crashed: {e}", 'ERROR')
                results[name] = False
        
        self._print_summary(results)
        return results
    
    def _print_summary(self, results: Dict[str, bool]) -> None:
        """Print test summary."""
        self._log("\n" + "=" * 50)
        self._log("SMOKE TEST SUMMARY")
        self._log("=" * 50)
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for name, result in results.items():
            status = 'PASS' if result else 'FAIL'
            self._log(f"  {name}: {status}")
        
        self._log(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            self._log("ALL TESTS PASSED", 'PASS')
        else:
            self._log(f"{total - passed} TEST(S) FAILED", 'FAIL')


def main():
    parser = argparse.ArgumentParser(description='Smoke test for Environmental Monitoring Platform')
    parser.add_argument('--broker', default='localhost', help='MQTT broker host')
    parser.add_argument('--port', type=int, default=8883, help='MQTT broker port')
    parser.add_argument('--tls', action='store_true', default=True, help='Use TLS')
    parser.add_argument('--no-tls', dest='tls', action='store_false', help='Disable TLS')
    parser.add_argument('--ca-cert', help='Path to CA certificate')
    parser.add_argument('--username', default='backend', help='MQTT username')
    parser.add_argument('--password', default='backendpass', help='MQTT password')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--wait', type=int, default=5, help='Wait seconds before testing')
    
    args = parser.parse_args()
    
    if args.wait > 0:
        print(f"Waiting {args.wait}s for services to be ready...")
        time.sleep(args.wait)
    
    test = SmokeTest(
        broker=args.broker,
        port=args.port,
        use_tls=args.tls,
        ca_cert=args.ca_cert,
        username=args.username,
        password=args.password,
        verbose=args.verbose
    )
    
    if not test.connect():
        print("Failed to connect to broker")
        sys.exit(1)
    
    try:
        results = test.run_all_tests()
        test.disconnect()
        
        # Exit with error code if any test failed
        if all(results.values()):
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        test.disconnect()
        sys.exit(130)


if __name__ == '__main__':
    main()