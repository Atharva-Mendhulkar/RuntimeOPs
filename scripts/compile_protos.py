import subprocess
import sys
from pathlib import Path

def main():
    project_root = Path(__file__).resolve().parent.parent
    proto_dir = project_root / "src" / "bob" / "api" / "protos"
    out_dir = project_root / "src" / "bob" / "api"
    
    print(f"Project root: {project_root}")
    print(f"Proto directory: {proto_dir}")
    print(f"Output directory: {out_dir}")
    
    # Run protoc
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={out_dir}",
        f"--pyi_out={out_dir}",
        f"--grpc_python_out={out_dir}",
        str(proto_dir / "bob.proto")
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("Protobuf compilation failed:")
        print(res.stderr)
        sys.exit(1)
        
    print("Protobuf compilation succeeded!")
    
    # Fix import in bob_pb2_grpc.py
    grpc_py_file = out_dir / "bob_pb2_grpc.py"
    if grpc_py_file.exists():
        content = grpc_py_file.read_text()
        # Replace local import with absolute package import
        fixed_content = content.replace(
            "import bob_pb2 as bob__pb2",
            "from bob.api import bob_pb2 as bob__pb2"
        )
        grpc_py_file.write_text(fixed_content)
        print(f"Fixed imports in {grpc_py_file.name}")

if __name__ == "__main__":
    main()
