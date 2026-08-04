# A recursive function used by longestPath. See below 
# link for details 
# https:#www.geeksforgeeks.org/topological-sorting/ 
def topologicalSortUtil(v,adj,V, Stack, visited):
    #global Stack, visited, adj
    visited[v] = True
  
    # Recur for all the vertices adjacent to this vertex 
    # list<AdjListNode>::iterator i 
    for i in adj[v]: 
        if (not visited[i[0]]): 
            V, Stack, visited = topologicalSortUtil(i[0],adj,V, Stack, visited) 
  
    # Push current vertex to stack which stores topological 
    # sort 
    Stack.append(v) 
    return V, Stack, visited
  
# The function to find longest distances from a given vertex. 
# It uses recursive topologicalSortUtil() to get topological 
# sorting. 
def longestPath(source,edges = []): 
    #global Stack, visited, V
    #global adj
    #編號頂點 
    node2ID = dict()
    cnt = 0
    for [x,y,w] in edges:
        for nod in [x,y]:
            if nod not in node2ID.keys():
                #print("="*50)
                #print(f"nod {nod} not in node2ID, adding")
                node2ID[nod] = cnt
                #print("nodeID af",node2ID)
                cnt += 1
    s = node2ID[source]
    V, Stack, visited = len(node2ID), [], [False for i in range(len(node2ID)+1)]
    #轉換edges為adj格式
    adj = [[] for i in range(len(node2ID)+1)]
    #print(node2ID)
    for [x,y,w] in edges:
        adj[node2ID[x]].append([node2ID[y],w])
    dist = [-10**9 for i in range(V)] 
  
    # Call the recursive helper function to store Topological 
    # Sort starting from all vertices one by one 
    for i in range(V): 
        if (visited[i] == False): 
            V, Stack, visited = topologicalSortUtil(i,adj,V, Stack, visited) 
    # print(Stack) 
  
    # Initialize distances to all vertices as infinite and 
    # distance to source as 0 
    dist[s] = 0
    # Stack.append(1) 
  
    # Process vertices in topological order 
    while (len(Stack) > 0): 
        
        # Get the next vertex from topological order 
        u = Stack[-1] 
        del Stack[-1] 
        #print(u) 
  
        # Update distances of all adjacent vertices 
        # list<AdjListNode>::iterator i 
        if (dist[u] != 10**9): 
            for i in adj[u]: 
                # print(u, i) 
                if (dist[i[0]] < dist[u] + i[1]): 
                    dist[i[0]] = dist[u] + i[1] 
  
    # Print calculated longest distances 
    # print(dist)
    #for i in range(V): 
        #print("INF ",end="") if (dist[i] == -10**9) else print(dist[i],end=" ")
    #ID2node = {_id:nod for nod,_id in node2ID.items()}
    #print(ID2node)
    #res = dict()
    res = {nod:dist[node2ID[nod]] for nod in node2ID}
    #print(res)
    return res
  
# Driver code 
if __name__ == '__main__': 
    V, Stack, visited = 6, [], [False for i in range(7)] 
    adj = [[] for i in range(7)]
      
    # Create a graph given in the above diagram. 
    # Here vertex numbers are 0, 1, 2, 3, 4, 5 with 
    # following mappings: 
    # 0=r, 1=s, 2=t, 3=x, 4=y, 5=z 
    adj[0].append([1, 5]) 
    adj[0].append([2, 3]) 
    adj[1].append([3, 6]) 
    adj[1].append([2, 2]) 
    adj[2].append([4, 4]) 
    adj[2].append([5, 2]) 
    adj[2].append([3, 7]) 
    adj[3].append([5, 1]) 
    adj[3].append([4, -1]) 
    adj[4].append([5, -2])
    print("adj",adj)
    edges = [
        ['r','s',5],
        ['r','t',3],
        ['s','x',6],
        ['s','t',2],
        ['t','y',4],
        ['t','z',2],
        ['t','x',7],
        ['x','z',1],
        ['x','y',-1],
        ['y','z',-2]
        ]

  
    s = 1
    #print("Following are longest distances from source vertex ",s) 
    #longestPath(source=s,edges=edges)
    s = 's'
    print("Following are longest distances from source vertex ",s) 
    print(longestPath(source=s,edges=edges))
  
    # This code is contributed by mohit kumar 29.