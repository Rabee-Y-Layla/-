import time
import random
from queue import Queue, Empty

class SelectiveRepeatARQ:
    """
    Implementation of Selective Repeat ARQ protocol with some optimizations
    Based on networking course project - version 2.3
    """
    
    def __init__(self, window_size, packet_loss_rate, total_packets=30):
        self.N = window_size  # window size
        self.p_loss = packet_loss_rate
        self.total_packets = total_packets
        
        # Sender side variables
        self.base_seq = 0
        self.next_seq_num = 0
        self.packet_timers = {}
        self.ack_received = set()
        self.transmission_count = 0
        self.last_ack_time = 0
        self.packet_retries = {}  # count retransmissions per packet
        
        # Receiver side  
        self.expected_seq = 0
        self.receiver_window = {}
        
        # Communication queues (simulate network channels)
        self.data_channel = Queue()
        self.ack_channel = Queue()
        
        self.simulation_start = 0
        self.finished = False
        
        # Some tuning parameters we found through testing
        self.BASE_TIMEOUT = 0.8
        self.STALL_LIMIT = 3.5
    
    def transmit_packet(self, seq_num):
        """Send packet with sequence number, simulate potential loss"""
        self.transmission_count += 1
        
        # Track how many times we've tried to send this packet
        if seq_num not in self.packet_retries:
            self.packet_retries[seq_num] = 0
        self.packet_retries[seq_num] += 1
        
        # Simulate packet loss based on probability
        if random.random() > self.p_loss:
            pkt = {
                'sequence': seq_num, 
                'is_ack': False, 
                'send_time': time.time()
            }
            self.data_channel.put(pkt)
            self.packet_timers[seq_num] = time.time()
            return True
        return False
    
    def send_acknowledgment(self, seq_num):
        """Send ACK for received packet, also subject to loss"""
        if random.random() > self.p_loss:
            ack_pkt = {
                'sequence': seq_num, 
                'is_ack': True, 
                'send_time': time.time()
            }
            self.ack_channel.put(ack_pkt)
            return True
        return False
    
    def calculate_timeout(self, seq_num):
        """Dynamic timeout based on retransmission count"""
        retry_count = self.packet_retries.get(seq_num, 0)
        # Increase timeout with retries, but not too much
        return self.BASE_TIMEOUT * (1.4 ** min(retry_count, 5))
    
    def execute_protocol(self):
        """Main protocol execution loop"""
        self.simulation_start = time.time()
        self.last_ack_time = self.simulation_start
        max_simulation_time = 25  # don't run forever
        
        print(f"Starting SRP test: window={self.N}, loss_rate={self.p_loss}")
        
        while self.base_seq < self.total_packets and time.time() - self.simulation_start < max_simulation_time:
            current_time = time.time()
            
            # Check if we're stuck - no progress for a while
            if current_time - self.last_ack_time > self.STALL_LIMIT:
                print(f"Detected stall at sequence {self.base_seq}, triggering recovery")
                self._recover_from_stall()
                self.last_ack_time = current_time
            
            # Try to send new packets in window
            sent_count = self._transmit_new_packets()
            if sent_count > 0:
                self.last_ack_time = current_time
            
            # Process any received data packets
            self._handle_data_reception()
            
            # Process any received ACKs
            self._process_acknowledgments()
            
            # Check for timed out packets
            self._check_timeouts()
            
            time.sleep(0.005)  # small delay to prevent CPU spinning
        
        self.finished = (self.base_seq >= self.total_packets)
        elapsed = time.time() - self.simulation_start
        
        print(f"Completed: final_seq={self.base_seq}, total_xmits={self.transmission_count}, "
              f"time={elapsed:.2f}s")
        
        return self.base_seq
    
    def _transmit_new_packets(self):
        """Send packets that are within the current window"""
        sent = 0
        while (self.next_seq_num < self.base_seq + self.N and 
               self.next_seq_num < self.total_packets):
            if self.next_seq_num not in self.ack_received:
                if self.transmit_packet(self.next_seq_num):
                    sent += 1
            self.next_seq_num += 1
        return sent
    
    def _handle_data_reception(self):
        """Process incoming data packets at receiver"""
        try:
            pkt = self.data_channel.get(timeout=0.01)
            if pkt and not pkt['is_ack']:
                seq = pkt['sequence']
                
                # Check if packet is within our receiving window
                window_start = self.expected_seq
                window_end = window_start + self.N - 1
                
                if window_start <= seq <= min(window_end, self.total_packets - 1):
                    if seq not in self.receiver_window:
                        self.receiver_window[seq] = True
                        self.send_acknowledgment(seq)
                    
                    # Deliver any in-order packets we can
                    while self.expected_seq in self.receiver_window:
                        del self.receiver_window[self.expected_seq]
                        self.expected_seq += 1
                        
                # If it's an old packet, still ACK it (might help sender)
                elif seq < window_start:
                    self.send_acknowledgment(seq)
                    
        except Empty:
            pass  # No packet received
    
    def _process_acknowledgments(self):
        """Process incoming ACKs at sender"""
        try:
            ack_pkt = self.ack_channel.get(timeout=0.01)
            if ack_pkt and ack_pkt['is_ack']:
                seq = ack_pkt['sequence']
                
                self.ack_received.add(seq)
                if seq in self.packet_timers:
                    del self.packet_timers[seq]
                
                # Reset retry counter for this packet
                if seq in self.packet_retries:
                    del self.packet_retries[seq]
                
                # Move window forward as much as possible
                while self.base_seq in self.ack_received:
                    self.base_seq += 1
                    self.last_ack_time = time.time()
                    
        except Empty:
            pass  # No ACK received
    
    def _check_timeouts(self):
        """Check for packets that need retransmission due to timeout"""
        current_time = time.time()
        expired_packets = []
        
        for seq, sent_time in list(self.packet_timers.items()):
            timeout_val = self.calculate_timeout(seq)
            if current_time - sent_time > timeout_val:
                expired_packets.append(seq)
        
        for seq in expired_packets:
            if seq not in self.ack_received and seq < self.total_packets:
                print(f"Timeout for packet {seq}, retransmitting (timeout={timeout_val:.2f}s)")
                self.transmit_packet(seq)
                self.packet_timers[seq] = current_time
    
    def _recover_from_stall(self):
        """Try to recover when protocol seems stuck"""
        print(f"Stall recovery: resetting from sequence {self.base_seq}")
        
        # Go back to current base and retransmit unacked packets
        self.next_seq_num = self.base_seq
        
        for seq in range(self.base_seq, min(self.base_seq + self.N, self.total_packets)):
            if seq not in self.ack_received:
                self.transmit_packet(seq)


def run_protocol_comparison():
    """Run comparison tests for the protocol"""
    print("SELECTIVE REPEAT ARQ - PERFORMANCE TEST")
    print("=" * 55)
    
    random.seed(42)  # For reproducible results
    
    test_scenarios = [
        (0.0, 4, "Ideal conditions"),
        (0.1, 4, "Low loss rate"),
        (0.2, 4, "Medium loss"), 
        (0.3, 4, "High loss"),
        (0.4, 4, "Very high loss"),
    ]
    
    print("\nSELECTIVE REPEAT ARQ RESULTS:")
    print("Scenario      | Efficiency | Progress | Status")
    print("-" * 50)
    
    for loss, window, description in test_scenarios:
        protocol = SelectiveRepeatARQ(window, loss, 30)
        delivered = protocol.execute_protocol()
        
        efficiency = protocol.transmission_count / delivered if delivered > 0 else 999
        status = "COMPLETE" if protocol.finished else "TIMEOUT"
        
        print(f"{description:13} | k={efficiency:5.2f}    | {delivered:2d}/30   | {status}")
    
    print("\nANALYSIS NOTES:")
    print("- SRP maintains good performance under moderate loss conditions")
    print("- Efficiency degrades gracefully as loss increases")
    print("- Window size 4 works well for most scenarios")
    print("- Timeout adaptation helps but has limits with very high loss")

if __name__ == "__main__":
    run_protocol_comparison()
