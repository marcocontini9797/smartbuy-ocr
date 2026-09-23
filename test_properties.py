from integrations.supabase.client import supabase


result = (
    supabase
    .table("properties")
    .select("*")
    .limit(10)
    .execute()
)


print(result.data)