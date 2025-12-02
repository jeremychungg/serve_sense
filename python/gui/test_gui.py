#!/usr/bin/env python3
"""
Test script for Serve Sense GUI components.

This script validates the GUI code structure without requiring a display.
"""

import sys
import pathlib
import ast

# Add parent directory to path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


def test_syntax():
    """Test Python syntax of GUI module."""
    gui_file = pathlib.Path(__file__).parent / "serve_sense_gui.py"
    
    print("Testing syntax...")
    with open(gui_file, 'r') as f:
        code = f.read()
    
    try:
        ast.parse(code)
        print("✓ Syntax check passed")
        return True
    except SyntaxError as e:
        print(f"✗ Syntax error: {e}")
        return False


def test_imports():
    """Test required imports."""
    print("\nTesting imports...")
    
    required_modules = [
        ('argparse', 'argparse'),
        ('asyncio', 'asyncio'),
        ('json', 'json'),
        ('math', 'math'),
        ('pathlib', 'pathlib'),
        ('struct', 'struct'),
        ('threading', 'threading'),
        ('collections', 'collections'),
        ('numpy', 'numpy'),
    ]
    
    all_ok = True
    for name, module in required_modules:
        try:
            __import__(module)
            print(f"✓ {name}")
        except ImportError as e:
            print(f"✗ {name}: {e}")
            all_ok = False
    
    return all_ok


def test_serve_labels():
    """Test serve_labels module integration."""
    print("\nTesting serve_labels integration...")
    
    try:
        from serve_labels import SERVE_LABELS, get_label_display_name
        
        assert len(SERVE_LABELS) == 9, "Expected 9 serve labels"
        print(f"✓ Found {len(SERVE_LABELS)} serve labels")
        
        # Test each label has a display name
        for label in SERVE_LABELS:
            display = get_label_display_name(label)
            assert display, f"No display name for {label}"
        
        print("✓ All labels have display names")
        
        # Print some examples
        print("\nExample labels:")
        for i, label in enumerate(SERVE_LABELS[:3]):
            print(f"  - {label} → {get_label_display_name(label)}")
        
        return True
        
    except Exception as e:
        print(f"✗ serve_labels error: {e}")
        return False


def test_packet_struct():
    """Test packet structure."""
    print("\nTesting packet structure...")
    
    import struct
    
    try:
        PACKET_STRUCT = struct.Struct("<IHH6fB3x")
        expected_size = 4 + 2 + 2 + 6*4 + 1 + 3  # 36 bytes
        actual_size = PACKET_STRUCT.size
        
        assert actual_size == expected_size, f"Expected {expected_size}, got {actual_size}"
        print(f"✓ Packet struct size: {actual_size} bytes")
        
        # Test packing/unpacking
        test_data = (12345, 1, 2, 0.1, 0.2, 0.3, 10.0, 20.0, 30.0, 0x01)
        packed = PACKET_STRUCT.pack(*test_data)
        unpacked = PACKET_STRUCT.unpack(packed)
        
        assert len(unpacked) == len(test_data), "Unpack size mismatch"
        print("✓ Pack/unpack test passed")
        
        return True
        
    except Exception as e:
        print(f"✗ Packet struct error: {e}")
        return False


def test_orientation_filter():
    """Test orientation filter logic."""
    print("\nTesting orientation filter...")
    
    import math
    
    try:
        # Simplified version of OrientationFilter
        class TestFilter:
            def __init__(self):
                self.roll = 0.0
                self.pitch = 0.0
            
            def update(self, ax, ay, az, gx, gy, gz):
                SAMPLE_DT = 0.01
                ALPHA = 0.02
                
                gx_r = math.radians(gx)
                gy_r = math.radians(gy)
                gz_r = math.radians(gz)
                
                self.roll += gx_r * SAMPLE_DT
                self.pitch += gy_r * SAMPLE_DT
                yaw = gz_r * SAMPLE_DT
                
                norm = math.sqrt(ax * ax + ay * ay + az * az) + 1e-6
                ax_n, ay_n, az_n = ax / norm, ay / norm, az / norm
                roll_acc = math.atan2(ay_n, az_n)
                pitch_acc = math.atan2(-ax_n, math.sqrt(ay_n * ay_n + az_n * az_n))
                
                self.roll = (1 - ALPHA) * self.roll + ALPHA * roll_acc
                self.pitch = (1 - ALPHA) * self.pitch + ALPHA * pitch_acc
                
                return self.roll, self.pitch, yaw
        
        filt = TestFilter()
        
        # Test with some sample data
        r, p, y = filt.update(0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
        assert -0.1 < r < 0.1, f"Expected roll ~0, got {r}"
        assert -0.1 < p < 0.1, f"Expected pitch ~0, got {p}"
        
        print("✓ Orientation filter logic validated")
        return True
        
    except Exception as e:
        print(f"✗ Orientation filter error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_structure():
    """Test GUI package file structure."""
    print("\nTesting file structure...")
    
    gui_dir = pathlib.Path(__file__).parent
    
    required_files = [
        "__init__.py",
        "serve_sense_gui.py",
        "README.md",
    ]
    
    all_ok = True
    for filename in required_files:
        filepath = gui_dir / filename
        if filepath.exists():
            print(f"✓ {filename}")
        else:
            print(f"✗ {filename} not found")
            all_ok = False
    
    return all_ok


def main():
    """Run all tests."""
    print("=" * 60)
    print("Serve Sense GUI - Validation Tests")
    print("=" * 60)
    
    tests = [
        ("Syntax", test_syntax),
        ("Imports", test_imports),
        ("Serve Labels", test_serve_labels),
        ("Packet Structure", test_packet_struct),
        ("Orientation Filter", test_orientation_filter),
        ("File Structure", test_file_structure),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Test {name} crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
