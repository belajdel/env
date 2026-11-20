#!/usr/bin/env python3
"""
Multi-Zone Environmental Monitoring Simulator
Publishes simulated sensor data to MQTT broker with anomaly injection capability.
"""

import argparse
import json
import signal
import sys
import time
import threading
from typing import Dict, Optional

from .config import ZONES, VALID_PARAMETERS, ANOMALY_TYPES, SAMPLING_INTERVAL, SEED
from .sensor_model import MultiZoneSimulator
from .mqtt_publisher import MultiZoneMQTTPublisher


class SimulatorApp:
    """Main simulator application."""
    
    def __init__(self, args):
        self.args = args
        self.running = False
        self.simulator = MultiZoneSimulator(seed=SEED)
        self.publisher = MultiZoneMQTTPublisher()
        self.publisher.initialize(self.simulator)
        self._publish_thread = None
        self._lock = threading.Lock()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print("\nShutdown signal received...")
        self.stop()
        
    def start(self) -> bool:
        """Start the simulator."""
        print("Starting Environmental Monitoring Simulator")
        print(f"Zones: {', '.join(ZONES)}")
        print(f"Parameters: {', '.join(VALID_PARAMETERS)}")
        print(f"Sampling interval: {SAMPLING_INTERVAL}s")
        print(f"MQTT Broker: {self.args.broker}:{self.args.port}")
        print(f"TLS: {'Enabled' if self.args.tls else 'Disabled'}")
        
        # Connect to MQTT
        print("\nConnecting to MQTT broker...")
        results = self.publisher.connect_all()
        connected_count = sum(1 for v in results.values() if v)
        print(f"Connected: {connected_count}/{len(ZONES)} zones")
        
        if connected_count == 0:
            print("ERROR: No zones connected to MQTT broker")
            return False
            
        self.running = True
        
        # Start publishing thread
        self._publish_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self._publish_thread.start()
        
        print("\nSimulator running. Press Ctrl+C to stop.")
        print("Commands available:")
        print("  inject <zone> <param> <type> [options]  - Inject anomaly")
        print("  clear <zone> <param>                    - Clear anomaly")
        print("  status                                  - Show status")
        print("  quit                                    - Stop simulator")
        
        # Command loop
        self._command_loop()
        return True
    
    def _publish_loop(self) -> None:
        """Main publishing loop."""
        next_publish = time.time()
        
        while self.running:
            now = time.time()
            
            if now >= next_publish:
                # Generate readings
                readings = self.simulator.generate_all_zones(now)
                
                # Publish
                results = self.publisher.publish_all_measurements(readings, now)
                
                # Log summary
                total_published = sum(
                    1 for zone_results in results.values() 
                    for success in zone_results.values() if success
                )
                total_failed = sum(
                    1 for zone_results in results.values() 
                    for success in zone_results.values() if not success
                )
                
                if self.args.verbose:
                    print(f"[{time.strftime('%H:%M:%S')}] Published: {total_published}, Failed/Dropout: {total_failed}")
                
                next_publish += SAMPLING_INTERVAL
            
            # Sleep until next interval
            sleep_time = max(0.1, next_publish - time.time())
            time.sleep(min(sleep_time, 1.0))
    
    def _command_loop(self) -> None:
        """Interactive command loop."""
        while self.running:
            try:
                cmd = input("\nsim> ").strip()
                if not cmd:
                    continue
                    
                parts = cmd.split()
                command = parts[0].lower()
                
                if command in ('quit', 'exit', 'q'):
                    break
                elif command == 'inject':
                    self._cmd_inject(parts[1:])
                elif command == 'clear':
                    self._cmd_clear(parts[1:])
                elif command == 'status':
                    self._cmd_status()
                elif command == 'help':
                    self._print_help()
                else:
                    print(f"Unknown command: {command}. Type 'help' for commands.")
                    
            except EOFError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Command error: {e}")
    
    def _cmd_inject(self, args: list) -> None:
        """Inject anomaly command."""
        if len(args) < 3:
            print("Usage: inject <zone> <param> <type> [magnitude=N] [duration=N] [rate=N] [probability=N]")
            print(f"  Zones: {', '.join(ZONES)}")
            print(f"  Params: {', '.join(VALID_PARAMETERS)}")
            print(f"  Types: {', '.join(ANOMALY_TYPES)}")
            return
            
        zone_id, param, anomaly_type = args[0], args[1], args[2]
        
        if zone_id not in ZONES:
            print(f"Invalid zone: {zone_id}")
            return
        if param not in VALID_PARAMETERS:
            print(f"Invalid parameter: {param}")
            return
        if anomaly_type not in ANOMALY_TYPES:
            print(f"Invalid anomaly type: {anomaly_type}")
            return
            
        # Parse additional options
        kwargs = {}
        for arg in args[3:]:
            if '=' in arg:
                key, value = arg.split('=', 1)
                try:
                    kwargs[key] = float(value) if '.' in value else int(value)
                except ValueError:
                    kwargs[key] = value
                    
        success = self.simulator.inject_anomaly(zone_id, param, anomaly_type, **kwargs)
        if success:
            print(f"Injected {anomaly_type} anomaly on {zone_id}/{param} with {kwargs}")
        else:
            print(f"Failed to inject anomaly")
    
    def _cmd_clear(self, args: list) -> None:
        """Clear anomaly command."""
        if len(args) < 2:
            print("Usage: clear <zone> <param>")
            return
            
        zone_id, param = args[0], args[1]
        self.simulator.clear_anomaly(zone_id, param)
        print(f"Cleared anomaly on {zone_id}/{param}")
    
    def _cmd_status(self) -> None:
        """Show status command."""
        print("\n=== Simulator Status ===")
        print(f"Running: {self.running}")
        print(f"MQTT Connections: {self.publisher.get_connection_status()}")
        
        print("\n--- Zone Status ---")
        for zone_id in ZONES:
            status = self.simulator.get_zone_status(zone_id)
            print(f"\n{zone_id}:")
            for param, sensor_status in status.get('sensors', {}).items():
                anomaly = sensor_status.get('anomaly_type', 'none')
                remaining = sensor_status.get('anomaly_remaining', 0)
                if anomaly != 'none':
                    print(f"  {param}: ANOMALY={anomaly} (remaining: {remaining})")
                else:
                    print(f"  {param}: OK")
    
    def _print_help(self) -> None:
        """Print help."""
        print("""
Commands:
  inject <zone> <param> <type> [options]  - Inject anomaly
    Types: spike, drift, stuck, dropout
    Options: magnitude=N, duration=N, rate=N, probability=N
    Example: inject prod-01 temperature spike magnitude=5 duration=10
  
  clear <zone> <param>                    - Clear anomaly
    Example: clear prod-01 temperature
  
  status                                  - Show all zone status
  
  help                                    - Show this help
  
  quit                                    - Stop simulator
""")
    
    def stop(self) -> None:
        """Stop the simulator."""
        print("\nStopping simulator...")
        self.running = False
        
        if self._publish_thread:
            self._publish_thread.join(timeout=5)
            
        self.publisher.publish_all_status("offline", "simulator_stopped")
        time.sleep(0.5)
        self.publisher.disconnect_all()
        
        print("Simulator stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Zone Environmental Monitoring Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Run with defaults
  %(prog)s --broker 192.168.1.100 --port 8883 # Custom broker
  %(prog)s --no-tls                           # Disable TLS
  %(prog)s --verbose                          # Verbose output
  %(prog)s --inject prod-01 temperature spike --magnitude 5 --duration 10  # Inject and run
        """
    )
    
    parser.add_argument('--broker', default='localhost', help='MQTT broker host')
    parser.add_argument('--port', type=int, default=8883, help='MQTT broker port')
    parser.add_argument('--tls', action='store_true', default=True, help='Use TLS (default)')
    parser.add_argument('--no-tls', dest='tls', action='store_false', help='Disable TLS')
    parser.add_argument('--interval', type=int, default=SAMPLING_INTERVAL, help='Sampling interval (seconds)')
    parser.add_argument('--seed', type=int, default=SEED, help='Random seed for reproducibility')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    # Anomaly injection from command line (run once and exit)
    parser.add_argument('--inject-zone', help='Zone ID for anomaly injection')
    parser.add_argument('--inject-param', help='Parameter for anomaly injection')
    parser.add_argument('--inject-type', choices=ANOMALY_TYPES, help='Anomaly type')
    parser.add_argument('--magnitude', type=float, default=3.0, help='Anomaly magnitude')
    parser.add_argument('--duration', type=int, default=10, help='Anomaly duration (samples)')
    parser.add_argument('--rate', type=float, default=0.5, help='Drift rate')
    parser.add_argument('--probability', type=float, default=0.5, help='Dropout probability')
    parser.add_argument('--run-once', action='store_true', help='Inject anomaly, publish once, and exit')
    
    args = parser.parse_args()
    
    # Override config with args
    import simulator.config as config
    config.MQTT_BROKER = args.broker
    config.MQTT_PORT = args.port
    config.MQTT_USE_TLS = args.tls
    config.SAMPLING_INTERVAL = args.interval
    config.SEED = args.seed
    
    app = SimulatorApp(args)
    
    # Handle one-shot anomaly injection
    if args.inject_zone and args.inject_param and args.inject_type:
        if not app.publisher.connect_all().get(args.inject_zone, False):
            print(f"Failed to connect to {args.inject_zone}")
            sys.exit(1)
            
        kwargs = {
            'magnitude': args.magnitude,
            'duration': args.duration,
            'rate': args.rate,
            'probability': args.probability,
        }
        
        app.simulator.inject_anomaly(args.inject_zone, args.inject_param, args.inject_type, **kwargs)
        
        if args.run_once:
            # Publish once and exit
            readings = app.simulator.generate_all_zones()
            app.publisher.publish_all_measurements(readings)
            time.sleep(1)
            app.publisher.disconnect_all()
            print("One-shot injection complete.")
            return
    
    # Run interactive
    try:
        success = app.start()
        sys.exit(0 if success else 1)
    finally:
        app.stop()


if __name__ == '__main__':
    main()