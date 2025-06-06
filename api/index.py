# File: api/index.py

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response # For generic responses to forward content
import httpx
import urllib.parse # To properly encode the URL parameter
import os # For potential future environment variables

# Initialize FastAPI app
app = FastAPI(
    title="TeleSocial Proxy API",
    description="A proxy API to fetch data from tele-social.vercel.app/down",
    version="1.0.0"
)

# The target API base URL
# You could also set this via an environment variable for more flexibility
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
    and returns the target API's response.
    """
    if not url:
        raise HTTPException(status_code=400, detail="The 'url' query parameter is required.")

    # Properly URL-encode the user-provided URL that will be part of the query string for the target API
    encoded_inner_url = urllib.parse.quote(url, safe='')
    
    # Construct the full URL to call the target API
    # The target API expects: https://tele-social.vercel.app/down?url=ENCODED_URL
    full_target_url = f"{TARGET_API_BASE_URL}?url={encoded_inner_url}"

    # Using httpx for asynchronous HTTP requests
    # Increased timeout as downloads can sometimes be slow
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        try:
            print(f"Proxying request to: {full_target_url}") # Log for Vercel console

            # Make the GET request to the target API
            upstream_response = await client.get(full_target_url)

            # Raise an exception for bad status codes (4xx or 5xx)
            # This helps in debugging and provides clearer errors to the client
            upstream_response.raise_for_status()

            # Get content-type from the upstream response, default if not present
            content_type = upstream_response.headers.get("content-type", "application/octet-stream")
            
            # Prepare headers for our response, primarily Content-Type
            # Also forward Content-Disposition if present, which is common for download endpoints
            response_headers = {"Content-Type": content_type}
            if "content-disposition" in upstream_response.headers:
                response_headers["Content-Disposition"] = upstream_response.headers["content-disposition"]
            
            # Return the raw content from the upstream API with its status code and relevant headers
            # This is crucial for correctly serving files like videos, images, etc.
            return Response(
                content=upstream_response.content, # Use .content for bytes
                status_code=upstream_response.status_code,
                headers=response_headers
            )

        except httpx.HTTPStatusError as exc:
            # Error from the target API (e.g., 404, 500 from tele-social)
            print(f"HTTPStatusError from upstream: Status {exc.response.status_code}, Response: {exc.response.text[:500]}...")
            raise HTTPException(
                status_code=exc.response.status_code, # Propagate the status code
                detail=f"Error from target API ({TARGET_API_BASE_URL}): {exc.response.text}"
            )
        except httpx.RequestError as exc:
            # Network error or other issue connecting to the target API
            print(f"RequestError connecting to upstream: {str(exc)}")
            raise HTTPException(
                status_code=502,  # Bad Gateway: indicates the proxy received an invalid response from upstream
                detail=f"Could not connect to the target API ({TARGET_API_BASE_URL}): {str(exc)}"
            )
        except Exception as e:
            # Catch any other unexpected errors
            print(f"An unexpected error occurred: {str(e)}")
            raise HTTPException(
                status_code=500, # Internal Server Error
                detail=f"An unexpected internal server error occurred: {str(e)}"
            )

# If you want to run this locally using `uvicorn api.index:app --reload`
# you might need to add this block, but Vercel handles this.
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)
