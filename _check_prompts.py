import asyncio
from app.services.supabase_client import get_client

async def main():
    client = get_client()
    resp = (
        client.table("generated_posts")
        .select("id,headline,image_prompt")
        .eq("job_id", "cdd36502-c4d1-4090-ad23-c4b0ce317b9e")
        .order("index")
        .execute()
    )
    for i, p in enumerate(resp.data, 1):
        print(f"=== Imagen {i} (post {p['id'][:8]}) ===")
        print(f"Headline: {p['headline']}")
        print(f"Image prompt:\n{p['image_prompt']}")
        print()

asyncio.run(main())
