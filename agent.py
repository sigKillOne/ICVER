import asyncio
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig

async def main():
    # 1. Configure the agent to have access to your local file system
    config = LocalAgentConfig(
        capabilities=CapabilitiesConfig(
            allow_file_write=True,
            allow_shell_execution=True 
        )
    )
    
    # 2. Initialize the agent using the async context manager
    async with Agent(config) as agent:
        
        # 3. The first prompt: Scaffolding the backend
        prompt = """
        I am building a project called ICVER. Please create a modular FastAPI backend structure in a folder named 'backend'.
        Create the following files with basic starter code:
        1. backend/main.py (FastAPI entry point)
        2. backend/api/router.py (For our /score and /consent endpoints)
        3. backend/core/config.py (For environment variables)
        4. backend/models/database.py (Setup for SQLAlchemy and MariaDB)
        5. backend/requirements.txt (Include fastapi, uvicorn, sqlalchemy, pymysql)
        """
        
        print("Starting the Antigravity agent... let it build the backend.")
        response = await agent.chat(prompt)
        
        # 4. Await and print the text response
        print("\nAgent Response:\n", await response.text())

if __name__ == "__main__":
    asyncio.run(main())