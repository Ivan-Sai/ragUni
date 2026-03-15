# How to Obtain MongoDB Atlas API Keys

## Why Are Atlas API Keys Needed?

With Atlas API keys your service can **automatically**:
- Create a Vector Search index on first launch
- Verify index configuration
- Update the index when necessary

**Without API keys** you must create the index manually (see VECTOR_SEARCH_SETUP.md).

---

## Step 1: Create API Keys in MongoDB Atlas

### 1.1 Open the Atlas Console

1. Go to https://cloud.mongodb.com/
2. Sign in to your account
3. In the upper-left corner, click on your organization name
4. Select **"Organization Access Manager"** or **"Access Manager"**

### 1.2 Create an API Key

1. Navigate to the **"API Keys"** tab
2. Click **"Create API Key"**

### 1.3 Configure Permissions

**Description:** `University Knowledge API`

**Permissions:** Select **"Organization Project Creator"** or **"Project Owner"**

**Minimum required permissions:**
- `Project Data Access Read Write` — for creating indexes
- `Project Cluster Manager` — for cluster management

3. Click **"Next"**

### 1.4 Save the Keys

**IMPORTANT:** The Private Key is displayed only once!

You will see:
- **Public Key** (e.g., `xvflmqwc`)
- **Private Key** (e.g., `12345678-1234-1234-1234-123456789abc`)

**Copy both keys!** The Private Key will not be shown again.

### 1.5 Add Your IP to the Whitelist (if required)

1. Click **"Add Access List Entry"**
2. Add:
   - `0.0.0.0/0` (for development — allow all IPs)
   - Or your specific IP address (for production)
3. Click **"Done"**

---

## Step 2: Find the Project ID and Cluster Name

### 2.1 Project ID

1. In the Atlas Dashboard, select your project
2. Click **"Settings"** in the left-hand menu
3. Copy the **"Project ID"**

It looks something like: `507f1f77bcf86cd799439011`

### 2.2 Cluster Name

1. Go to **"Database"** in the left-hand menu
2. Find the name of your cluster (typically `Cluster0`)

---

## Step 3: Add Credentials to backend/.env

Open `backend/.env` and add or update the following:

```bash
# MongoDB Atlas API (for automatic Vector Search index creation)
ATLAS_PUBLIC_KEY=xvflmqwc
ATLAS_PRIVATE_KEY=12345678-1234-1234-1234-123456789abc
ATLAS_PROJECT_ID=507f1f77bcf86cd799439011
ATLAS_CLUSTER_NAME=Cluster0
```

**Replace** the values with your actual credentials!

---

## Step 4: Verification

Restart your service from the `backend/` directory:

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see output similar to:

```
Starting University Knowledge API...
Connected to MongoDB Atlas
Database indexes created
Checking vector search index 'vector_index'...
Index 'vector_index' exists
   Status: STEADY
Vector Search index ready
```

If the index does not exist, the service will create it automatically:

```
Creating vector search index 'vector_index'...
Vector search index 'vector_index' created successfully
Index is building... This may take 1-2 minutes
Vector Search index ready
```

---

## Security

### Important Rules:

1. **DO NOT commit** the `.env` file to git
2. **DO NOT share** the Private Key with anyone
3. **Use** the IP whitelist in production
4. **Rotate** keys regularly (every 3-6 months)

### For Production:

1. Use more restrictive permissions (limit to required projects only)
2. Add only specific IP addresses
3. Use separate keys for dev/staging/production
4. Enable audit logging in Atlas

---

## Troubleshooting

### Error: "401 Unauthorized"

**Cause:** Incorrect Public/Private keys

**Solution:**
1. Verify the keys in `backend/.env` are correct
2. Make sure there are no extra spaces
3. Create a new key pair

### Error: "403 Forbidden"

**Cause:** Insufficient permissions for the API key

**Solution:**
1. Go to Atlas -> API Keys
2. Find your key
3. Add `Project Cluster Manager` permissions

### Error: "IP not whitelisted"

**Cause:** Your IP is not in the whitelist

**Solution:**
1. Go to Atlas -> API Keys -> your key
2. Access List -> Add Entry
3. Add `0.0.0.0/0` or your IP

### Service starts but the index is not created

**Cause:** Atlas API credentials are not configured or are incorrect

**Solution:**
1. Verify that all 4 variables are set in `backend/.env`
2. Check the service startup logs
3. If you see `Atlas API not configured` — review `backend/.env`

---

## Alternative: Manual Index Creation

If you prefer not to use API keys, you can create the index manually.

See the detailed instructions in: **VECTOR_SEARCH_SETUP.md**

---

## Useful Links

- [MongoDB Atlas API Documentation](https://www.mongodb.com/docs/atlas/configure-api-access/)
- [API Authentication](https://www.mongodb.com/docs/atlas/configure-api-access/#std-label-atlas-admin-api-access)
- [Search Index Management API](https://www.mongodb.com/docs/atlas/reference/api-resources-spec/v2/#tag/Atlas-Search)

---

## Checklist

- [ ] Created API keys in Atlas
- [ ] Saved Public Key and Private Key
- [ ] Found Project ID
- [ ] Found Cluster Name
- [ ] Added all 4 parameters to `backend/.env`
- [ ] Restarted the service
- [ ] Confirmed "Vector Search index ready" appears in the logs
- [ ] Verified that `.env` is excluded from git (`.gitignore`)

**Once all items are complete, automatic index creation is operational.**
