from sentence_transformers import SentenceTransformer
import hdbscan
import pandas as pd
import numpy as np

print("Loading Embedding Model...")
model = SentenceTransformer('all-MiniLM-L6-v2')

def cluster_posts(posts_data):
    """
    Input: List of dicts [{'id': '...', 'text': '...'}]
    Output: Dictionary mapping Cluster ID to list of posts
    """
    if len(posts_data) < 5:
        print("Not enough data to cluster.")
        return {}

    # 1. Prepare Data
    documents = [p['text'] for p in posts_data]
    
    # 2. Embed
    # Convert to numpy array for math operations later
    embeddings = model.encode(documents) 

    # 3. Cluster
    clusterer = hdbscan.HDBSCAN(min_cluster_size=3, min_samples=1, metric='euclidean')
    cluster_labels = clusterer.fit_predict(embeddings)

    # 4. Organize Results
    df = pd.DataFrame(posts_data)
    df['cluster'] = cluster_labels
    df['embedding_index'] = df.index # Track original index to lookup embedding
    
    valid_clusters = df[df['cluster'] != -1]
    unique_clusters = valid_clusters['cluster'].unique()
    
    results = {}
    
    print(f"Found {len(unique_clusters)} valid clusters.")
    
    for label in unique_clusters:
        # Get dataframe slice for this cluster
        cluster_df = valid_clusters[valid_clusters['cluster'] == label].copy()
        
        # --- NEW: CENTROID LOGIC ---
        # Get the actual vectors for just this cluster
        indices = cluster_df['embedding_index'].values
        cluster_vectors = embeddings[indices]
        
        # Calculate the mathematical center (mean) of these vectors
        centroid = np.mean(cluster_vectors, axis=0)
        
        # Calculate distance of every post to that center
        # (Linear Algebra: Euclidean distance)
        distances = np.linalg.norm(cluster_vectors - centroid, axis=1)
        
        # Find the index of the closest post (The "Centroid Post")
        closest_local_index = np.argmin(distances)
        
        # Mark the posts in the dataframe
        cluster_df['is_centroid'] = False
        cluster_df.iloc[closest_local_index, cluster_df.columns.get_loc('is_centroid')] = True
        # ---------------------------

        # Sort by engagement (highest first) for the rest
        cluster_df = cluster_df.sort_values(by='engagement', ascending=False)
        
        # Convert to dict
        results[int(label)] = cluster_df.to_dict('records')

    return results