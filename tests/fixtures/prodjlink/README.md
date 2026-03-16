# Pro DJ Link Packet Capture Fixtures

Place captured Pro DJ Link UDP packet files here for use in Layer 1B tests.

## Capture format

Captures are stored as JSON files, each containing a list of packets:

```json
[
  { "src_ip": "169.254.11.53", "src_port": 50000, "timestamp": 1700000000.0, "data_hex": "5173..." },
  ...
]
```

## How to capture

Use tcpdump on the Pioneer interface:
```bash
sudo tcpdump -i en16 -w capture.pcap udp port 50000 or udp port 50001
```

Then convert to the JSON format using tools/mock_prodjlink.py.

## Milestone 2 testing

Captured sessions are used to:
- Verify the cursor tracks correctly across a full DJ set
- Test tempo change handling (pitch fader movement)
- Test deck switching (master deck changes)
- Test enrichment pass triggering (first track load)
