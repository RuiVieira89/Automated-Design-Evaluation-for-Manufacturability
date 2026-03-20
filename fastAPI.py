from fastapi import FastAPI, UploadFile, File
import trimesh
import io

app = FastAPI()

@app.get("/")
def read_root():
    return {"Status": "CAD API is Online"}

@app.post("/analyze_stl")
async def analyze_stl(file: UploadFile = File(...)):
    # 1. Read the uploaded file into memory
    contents = await file.read()
    
    # 2. Load into Trimesh using a file-like object
    # We provide 'stl' as the file_type since we're reading raw bytes
    mesh = trimesh.load(io.BytesIO(contents), file_type='stl')
    
    # 3. Perform Manufacturability Checks
    analysis = {
        "filename": file.filename,
        "is_watertight": mesh.is_watertight,
        "volume_mm3": round(mesh.volume, 2),
        "surface_area_mm2": round(mesh.area, 2),
        "bounding_box_dims": mesh.extents.tolist(), # [Length, Width, Height]
        "center_of_mass": mesh.center_mass.tolist()
    }
    
    return analysis

'''
To run this FastAPI server, use the command:

uvicorn fastAPI:app --reload
'''
