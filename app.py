from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
from google.protobuf.message import DecodeError
import ssl
import warnings
import os

# Suppress SSL warnings
warnings.filterwarnings("ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Configuration
API_KEY = "ghost_modx"  # You can change this or load from environment variable
REQUEST_COUNT = 100  # Number of requests to send
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'False').lower() == 'true'  # Enable/disable debug mode

def load_tokens(server_name):
    """Load tokens based on server region"""
    try:
        token_files = {
            "IND": "token_ind.json",
            "BR": "token_br.json",
            "US": "token_br.json",
            "SAC": "token_br.json",
            "NA": "token_br.json",
            "BD": "token_bd.json"
        }
        
        filename = token_files.get(server_name, "token_bd.json")
        
        with open(filename, "r") as f:
            tokens = json.load(f)
            
        if not tokens:
            app.logger.error(f"No tokens found in {filename}")
            return None
            
        if DEBUG_MODE:
            app.logger.info(f"Loaded {len(tokens)} tokens from {filename}")
            
        return tokens
    except FileNotFoundError as e:
        app.logger.error(f"Token file not found: {e}")
        return None
    except json.JSONDecodeError as e:
        app.logger.error(f"Invalid JSON in token file: {e}")
        return None
    except Exception as e:
        app.logger.error(f"Error loading tokens for server {server_name}: {e}")
        return None

def encrypt_message(plaintext):
    """Encrypt message using AES-CBC"""
    try:
        key = b'Yg&tc%DEuh6%Zc^8'
        iv = b'6oyZDr22E3ychjM%'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_message = pad(plaintext, AES.block_size)
        encrypted_message = cipher.encrypt(padded_message)
        encrypted_hex = binascii.hexlify(encrypted_message).decode('utf-8')
        
        if DEBUG_MODE:
            app.logger.debug(f"Encrypted message length: {len(encrypted_hex)}")
            
        return encrypted_hex
    except Exception as e:
        app.logger.error(f"Error encrypting message: {e}")
        return None

def create_protobuf_message(user_id, region):
    """Create like protobuf message"""
    try:
        message = like_pb2.like()
        message.uid = int(user_id)
        message.region = region
        
        if DEBUG_MODE:
            app.logger.debug(f"Created like protobuf for UID: {user_id}, Region: {region}")
            
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating protobuf message: {e}")
        return None

async def send_request(encrypted_uid, token, url, session, request_id):
    """Send single like request"""
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB49"
        }
        
        if DEBUG_MODE:
            app.logger.debug(f"Sending request {request_id} to {url}")
        
        async with session.post(url, data=edata, headers=headers, ssl=False, timeout=30) as response:
            if response.status != 200:
                app.logger.error(f"Request {request_id} failed with status code: {response.status}")
                return {"status": response.status, "success": False, "request_id": request_id}
            
            await response.text()
            
            if DEBUG_MODE:
                app.logger.debug(f"Request {request_id} completed successfully")
                
            return {"status": response.status, "success": True, "request_id": request_id}
            
    except asyncio.TimeoutError:
        app.logger.error(f"Request {request_id} timeout")
        return {"status": 408, "success": False, "request_id": request_id}
    except Exception as e:
        app.logger.error(f"Exception in send_request {request_id}: {e}")
        return {"status": 500, "success": False, "request_id": request_id, "error": str(e)}

async def send_multiple_requests(uid, server_name, url):
    """Send multiple like requests concurrently"""
    try:
        region = server_name
        protobuf_message = create_protobuf_message(uid, region)
        if protobuf_message is None:
            app.logger.error("Failed to create protobuf message.")
            return None
            
        encrypted_uid = encrypt_message(protobuf_message)
        if encrypted_uid is None:
            app.logger.error("Encryption failed.")
            return None
            
        tokens = load_tokens(server_name)
        if tokens is None or not tokens:
            app.logger.error("Failed to load tokens.")
            return None
            
        if DEBUG_MODE:
            app.logger.info(f"Preparing to send {REQUEST_COUNT} requests to {server_name} server")
        
        # Create a connector with SSL disabled
        connector = aiohttp.TCPConnector(ssl=False, limit=100)  # Limit concurrent connections
        
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            for i in range(REQUEST_COUNT):
                token = tokens[i % len(tokens)]["token"]
                tasks.append(send_request(encrypted_uid, token, url, session, i+1))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successful requests
            successful = sum(1 for r in results if isinstance(r, dict) and r.get("success", False))
            
            if DEBUG_MODE:
                app.logger.info(f"Sent {REQUEST_COUNT} requests, {successful} successful, {REQUEST_COUNT - successful} failed")
            
            return results
            
    except Exception as e:
        app.logger.error(f"Exception in send_multiple_requests: {e}")
        return None

def create_protobuf(uid):
    """Create UID protobuf message"""
    try:
        message = uid_generator_pb2.uid_generator()
        message.saturn_ = int(uid)
        message.garena = 1
        
        if DEBUG_MODE:
            app.logger.debug(f"Created UID protobuf for UID: {uid}")
            
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating uid protobuf: {e}")
        return None

def enc(uid):
    """Encrypt UID"""
    protobuf_data = create_protobuf(uid)
    if protobuf_data is None:
        return None
    encrypted_uid = encrypt_message(protobuf_data)
    return encrypted_uid

def get_url(server_name, endpoint):
    """Get URL based on server region and endpoint"""
    urls = {
        "IND": {
            "personal": "https://client.ind.freefiremobile.com/GetPlayerPersonalShow",
            "like": "https://client.ind.freefiremobile.com/LikeProfile"
        },
        "BR": {
            "personal": "https://client.us.freefiremobile.com/GetPlayerPersonalShow",
            "like": "https://client.us.freefiremobile.com/LikeProfile"
        },
        "US": {
            "personal": "https://client.us.freefiremobile.com/GetPlayerPersonalShow",
            "like": "https://client.us.freefiremobile.com/LikeProfile"
        },
        "SAC": {
            "personal": "https://client.us.freefiremobile.com/GetPlayerPersonalShow",
            "like": "https://client.us.freefiremobile.com/LikeProfile"
        },
        "NA": {
            "personal": "https://client.us.freefiremobile.com/GetPlayerPersonalShow",
            "like": "https://client.us.freefiremobile.com/LikeProfile"
        },
        "BD": {
            "personal": "https://clientbp.ggblueshark.com/GetPlayerPersonalShow",
            "like": "https://clientbp.ggblueshark.com/LikeProfile"
        }
    }
    
    default_urls = {
        "personal": "https://clientbp.ggblueshark.com/GetPlayerPersonalShow",
        "like": "https://clientbp.ggblueshark.com/LikeProfile"
    }
    
    server_urls = urls.get(server_name, default_urls)
    url = server_urls.get(endpoint, default_urls[endpoint])
    
    if DEBUG_MODE:
        app.logger.debug(f"URL for {server_name}/{endpoint}: {url}")
    
    return url

def make_request(encrypt, server_name, token):
    """Make request to get player info"""
    try:
        url = get_url(server_name, "personal")
        edata = bytes.fromhex(encrypt)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB49"
        }
        
        if DEBUG_MODE:
            app.logger.debug(f"Making request to {url}")
        
        response = requests.post(url, data=edata, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        
        binary = response.content
        
        if DEBUG_MODE:
            app.logger.debug(f"Received response of length: {len(binary)} bytes")
        
        decode = decode_protobuf(binary)
        if decode is None:
            app.logger.error("Protobuf decoding returned None.")
        return decode
        
    except requests.exceptions.Timeout:
        app.logger.error("Request timeout")
        return None
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request error: {e}")
        return None
    except Exception as e:
        app.logger.error(f"Error in make_request: {e}")
        return None

def decode_protobuf(binary):
    """Decode protobuf binary data"""
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        
        if DEBUG_MODE:
            app.logger.debug("Protobuf decoded successfully")
            
        return items
    except DecodeError as e:
        app.logger.error(f"Error decoding Protobuf data: {e}")
        return None
    except Exception as e:
        app.logger.error(f"Unexpected error during protobuf decoding: {e}")
        return None

@app.route('/like', methods=['GET'])
def handle_requests():
    """Main endpoint to handle like requests"""
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "").upper()
    key = request.args.get("key", "")
    
    if DEBUG_MODE:
        app.logger.info(f"Received request - UID: {uid}, Server: {server_name}, Key: {'*' * len(key) if key else 'None'}")
    
    # API Key Validation
    if key != API_KEY:
        app.logger.warning(f"Invalid API key attempt: {key}")
        return jsonify({"error": "INVALID API KEY", "status": "error"}), 403
    
    if not uid:
        return jsonify({"error": "UID is required", "status": "error"}), 400
    
    valid_servers = ["IND", "BR", "US", "SAC", "NA", "BD"]
    if not server_name or server_name not in valid_servers:
        return jsonify({
            "error": f"Invalid or missing server_name. Valid options: {', '.join(valid_servers)}", 
            "status": "error"
        }), 400
    
    try:
        # Load tokens
        tokens = load_tokens(server_name)
        if tokens is None or not tokens:
            return jsonify({"error": f"Failed to load tokens for server: {server_name}", "status": "error"}), 500
        
        # Get token for initial request
        token = tokens[0]['token']
        
        if DEBUG_MODE:
            app.logger.info(f"Using token: {token[:10]}...")
        
        # Encrypt UID
        encrypted_uid = enc(uid)
        if encrypted_uid is None:
            return jsonify({"error": "Encryption of UID failed", "status": "error"}), 500
        
        # Get initial likes count
        before_info = make_request(encrypted_uid, server_name, token)
        if before_info is None:
            return jsonify({"error": "Failed to retrieve initial player info", "status": "error"}), 500
        
        try:
            jsone = MessageToJson(before_info)
            data_before = json.loads(jsone)
            before_like = int(data_before.get('AccountInfo', {}).get('Likes', 0))
            
            if DEBUG_MODE:
                app.logger.info(f"Initial likes count: {before_like}")
                
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            app.logger.error(f"Error parsing initial response: {e}")
            before_like = 0
        
        # Get like URL
        like_url = get_url(server_name, "like")
        
        # Send multiple like requests
        results = asyncio.run(send_multiple_requests(uid, server_name, like_url))
        
        if results is None:
            return jsonify({"error": "Failed to send like requests", "status": "error"}), 500
        
        # Small delay to ensure likes are processed
        import time
        time.sleep(2)
        
        # Get after likes count
        after_info = make_request(encrypted_uid, server_name, token)
        if after_info is None:
            return jsonify({"error": "Failed to retrieve updated player info", "status": "error"}), 500
        
        try:
            jsone_after = MessageToJson(after_info)
            data_after = json.loads(jsone_after)
            after_like = int(data_after.get('AccountInfo', {}).get('Likes', 0))
            player_uid = int(data_after.get('AccountInfo', {}).get('UID', 0))
            player_name = str(data_after.get('AccountInfo', {}).get('PlayerNickname', ''))
            
            if DEBUG_MODE:
                app.logger.info(f"After likes count: {after_like}")
                app.logger.info(f"Player: {player_name} (UID: {player_uid})")
                
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            app.logger.error(f"Error parsing after response: {e}")
            after_like = before_like
            player_uid = int(uid)
            player_name = ""
        
        like_given = after_like - before_like
        status = 1 if like_given > 0 else 2
        
        # Calculate success rate
        successful_requests = 0
        failed_requests = []
        
        for r in results:
            if isinstance(r, dict):
                if r.get("success", False):
                    successful_requests += 1
                else:
                    failed_requests.append(r.get("status", "unknown"))
        
        result = {
            "LikesGivenByAPI": like_given,
            "LikesbeforeCommand": before_like,
            "LikesafterCommand": after_like,
            "PlayerNickname": player_name,
            "UID": player_uid,
            "server": server_name,
            "status": status,
            "successful_requests": successful_requests,
            "total_requests": REQUEST_COUNT,
            "failed_requests": len(failed_requests),
            "Telegram_Channel": "YOUR_CNL_NAME",
            "Contact_Developer": "YOUR_USERNAME"
        }
        
        if DEBUG_MODE:
            result["debug_info"] = {
                "debug_mode": True,
                "failed_statuses": list(set(failed_requests))[:10]  # Show first 10 unique failed statuses
            }
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error processing request: {e}", exc_info=True)
        return jsonify({"error": str(e), "status": "error"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "service": "FreeFire Like API",
        "debug_mode": DEBUG_MODE,
        "supported_servers": ["IND", "BR", "US", "SAC", "NA", "BD"]
    })

@app.route('/config', methods=['GET'])
def get_config():
    """Get current configuration (only in debug mode)"""
    if not DEBUG_MODE:
        return jsonify({"error": "Not available in production mode"}), 403
    
    return jsonify({
        "debug_mode": DEBUG_MODE,
        "request_count": REQUEST_COUNT,
        "supported_servers": ["IND", "BR", "US", "SAC", "NA", "BD"]
    })

if __name__ == '__main__':
    # Get port from environment variable or default to 5000
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    
    # Enable debug mode based on environment variable
    debug = DEBUG_MODE
    
    print(f"Starting FreeFire Like API Server...")
    print(f"Debug Mode: {debug}")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Supported Servers: IND, BR, US, SAC, NA, BD")
    print(f"Request Count: {REQUEST_COUNT}")
    
    # Run with proper settings
    app.run(host=host, port=port, debug=debug, use_reloader=False)
