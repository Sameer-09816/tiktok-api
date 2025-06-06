# File: api/index.py

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware # Import CORSMiddleware
import httpx
import urllib.parse
import os

# Initialize FastAPI app
app = FastAPI(
    title="TeleSocial Proxy API",
    description="A proxy API to fetch data from tele-social.vercel.app/down. Allows requests from any origin.",
    version="1.0.1"
)

# Add CORSMiddleware
# This allows requests from any origin, with any method, and any headers.
# This is crucial if your API will be consumed by browser-based applications from different domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True, # Allows cookies to be included if needed (though likely not for this proxy)
    allow_methods=["*"],  # Allows all common HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# The target API base URL
TARGET_API_BASE_URL = os.getenv("TARGET_API_BASE_URL", "https://tele-social.vercel.app/down")

@app.get("/")
async def root():
    """
    Root endpoint for health check or basic info.
    """
    return {"message": "Welcome to the TeleSocial Proxy API. Use /api/proxy?url=<target_url> to make a request."}

@app.get("/api/proxy")
async def proxy_request(
    url: str = Query(..., description="The URL to be processed by the target API (e.g., a Telegram post URL). This URL will be URL-encoded before being passed to the target.")
):
    """
    Proxies a request to the tele-social API.
    It takes a 'url' query parameter, forwards it to the target API,
    and returns the target API's response, including appropriate headers.
    """
    if not url:
        raise HTTPException(status_code=400, detail="The 'url' query parameter is required.")

    # Properly URL-encode the user-provided URL that will be part of the query string for the target API
    encoded_inner_url = urllib.parse.quote(url, safe='')
    
    full_target_url = f"{TARGET_API_BASE_URL}?url={encoded_inner_url}"

    # Using httpx for asynchronous HTTP requests
    # Increased timeout as downloads can sometimes be slow
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        try:
            print(f"Proxying request to: {full_target_url}") # Log for Vercel console

            upstream_response = await client.get(full_target_url)
            upstream_response.raise_for_status() # Raise an exception for 4xx/5xx status codes

            # Get content-type from the upstream response, default if not present
            content_type = upstream_response.headers.get("content-type", "application/octet-stream")
            
            # Prepare headers for our response.
            # FastAPI's CORSMiddleware will add Access-Control-Allow-Origin and other CORS headers.
            # We primarily need to forward content-specific headers from the upstream.
            response_headers = {"Content-Type": content_type}
            if "content-disposition" in upstream_response.headers:
                response_headers["Content-Disposition"] = upstream_response.headers["content-disposition"]
            
            # Return the raw content from the upstream API with its status code and relevant headers
            return Response(
                content=upstream_response.content,
                status_code=upstream_response.status_code,
                headers=response_headers
            )

        except httpx.HTTPStatusError as exc:
            # Error from the target API (e.g., 404, 500 from tele-social)
            print(f"HTTPStatusError from upstream: Status {exc.response.status_code}, Response: {exc.response.text[:500]}...")
            # CORSMiddleware will ensure this error response also has CORS headers
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Error from target API ({TARGET_API_BASE_URL}): {exc.response.text}"
            )
        except httpx.RequestError as exc:
            # Network error or other issue connecting to the target API
            print(f"RequestError connecting to upstream: {str(exc)}")
            raise HTTPException(
                status_code=502,  # Bad Gateway
                detail=f"Could not connect to the target API ({TARGET_API_BASE_URL}): {str(exc)}"
            )
        except Exception as e:
            # Catch any other unexpected errors
            print(f"An unexpected error occurred: {str(e)}")
            raise HTTPException(
                status_code=500, # Internal Server Error
                detail=f"An unexpected internal server error occurred: {str(e)}"
            )

# Note: No `if __name__ == "__main__":` block is strictly needed for Vercel deployment,
# but useful for local testing with `uvicorn api.index:app --reload`.
