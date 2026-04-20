from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from vasp.a2v.v3.new_flow_pipeline_v3 import run_pipeline

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://theextraordinary.github.io",
        "https://anigma.in"
    ],
    allow_methods=["*"],
    allow_headers=["*"]
)

class VASPRequest(BaseModel):
    prompt:str
    funny:float=0.3
    duration:int=30

@app.post("/generate")
async def generate(req:VASPRequest):

    output = run_pipeline(
        query=req.prompt,
        funny=req.funny,
        duration=req.duration
    )

    return {
        "result":output
    }