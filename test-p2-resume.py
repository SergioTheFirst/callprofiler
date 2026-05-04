import sys
sys.path.insert(0, 'src')

from callprofiler.config import load_config
from callprofiler.db.repository import Repository
from callprofiler.biography.repo import BiographyRepo
from callprofiler.analyze.llm_client import LLMClient
from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography import p2_entities

cfg = load_config('configs/base.yaml')
repo = Repository('C:/calls/data/db/callprofiler.db')
bio = BiographyRepo(repo)

llm_core = LLMClient(base_url=cfg.models.llm_url, timeout=300)
rllm = ResilientLLMClient(llm_core, bio, model_name='qwen3.5-9b', max_retries=3)

print("Running p2_entities with resume support...")
result = p2_entities.run(user_id='serhio', bio=bio, llm=rllm)
print("Result:", result)
