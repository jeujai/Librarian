// Neo4j Health Check Script
// This script performs comprehensive health checks to ensure Neo4j is working properly

// Basic connectivity and version test
CALL dbms.components() YIELD name, versions, edition
WITH name, versions[0] as version, edition
WHERE name = "Neo4j Kernel"
RETURN "Neo4j Connectivity" as check_name, "OK" as status, 
       name + " " + version + " (" + edition + ")" as details, 
       datetime() as timestamp;

// Check available memory
CALL dbms.queryJvm("java.lang:type=Memory") YIELD attributes
WITH attributes.HeapMemoryUsage.used as heapUsed, 
     attributes.HeapMemoryUsage.max as heapMax,
     attributes.NonHeapMemoryUsage.used as nonHeapUsed
RETURN "Memory Usage" as check_name,
       CASE WHEN heapUsed < heapMax * 0.8 THEN "OK" 
            WHEN heapUsed < heapMax * 0.9 THEN "WARNING"
            ELSE "CRITICAL" END as status,
       "Heap: " + toString(round(heapUsed/1024.0/1024.0)) + "MB/" + 
       toString(round(heapMax/1024.0/1024.0)) + "MB, NonHeap: " + 
       toString(round(nonHeapUsed/1024.0/1024.0)) + "MB" as details,
       datetime() as timestamp;

// Check if APOC plugin is available and working
CALL apoc.version() YIELD version
RETURN "APOC Plugin" as check_name, "OK" as status, 
       "APOC version: " + version as details, datetime() as timestamp
UNION ALL

// Test APOC functionality
CALL apoc.date.format(timestamp(), 'ms', 'yyyy-MM-dd HH:mm:ss') YIELD value
RETURN "APOC Functionality" as check_name, "OK" as status,
       "Date formatting works: " + value as details, datetime() as timestamp;

// Check if GDS plugin is available
CALL gds.version() YIELD version
RETURN "GDS Plugin" as check_name, "OK" as status,
       "GDS version: " + version as details, datetime() as timestamp;

// Check database statistics and health
CALL db.stats.retrieve('GRAPH COUNTS') YIELD data
WITH data.nodes as nodeCount, data.relationships as relCount
RETURN "Database Statistics" as check_name, "INFO" as status,
       "Nodes: " + toString(nodeCount) + ", Relationships: " + toString(relCount) as details,
       datetime() as timestamp;

// Check for long-running transactions
CALL dbms.listTransactions() YIELD transactionId, currentQuery, elapsedTimeMillis
WITH count(*) as totalTx, 
     sum(CASE WHEN elapsedTimeMillis > 30000 THEN 1 ELSE 0 END) as longRunningTx
RETURN "Transaction Health" as check_name,
       CASE WHEN longRunningTx = 0 THEN "OK"
            WHEN longRunningTx < 3 THEN "WARNING"
            ELSE "CRITICAL" END as status,
       "Total: " + toString(totalTx) + ", Long-running (>30s): " + toString(longRunningTx) as details,
       datetime() as timestamp;

// Check constraints and indexes
CALL db.constraints() YIELD name, type
WITH count(*) as constraintCount
RETURN "Constraints" as check_name, "INFO" as status,
       "Total constraints: " + toString(constraintCount) as details,
       datetime() as timestamp
UNION ALL

CALL db.indexes() YIELD name, type, state
WITH count(*) as totalIndexes, 
     sum(CASE WHEN state = "ONLINE" THEN 1 ELSE 0 END) as onlineIndexes
RETURN "Indexes" as check_name,
       CASE WHEN onlineIndexes = totalIndexes THEN "OK" ELSE "WARNING" END as status,
       "Total: " + toString(totalIndexes) + ", Online: " + toString(onlineIndexes) as details,
       datetime() as timestamp;

// Performance test - simple query with timing
CALL apoc.util.sleep(1) // Small delay to separate from other queries
WITH timestamp() as startTime
MATCH (n) 
WITH startTime, count(n) as nodeCount, timestamp() as endTime
RETURN "Performance Test" as check_name,
       CASE WHEN (endTime - startTime) < 1000 THEN "OK"
            WHEN (endTime - startTime) < 5000 THEN "WARNING"
            ELSE "CRITICAL" END as status,
       "Node count query: " + toString(nodeCount) + " nodes in " + 
       toString(endTime - startTime) + "ms" as details,
       datetime() as timestamp;

// Check node label distribution (top 10)
CALL db.labels() YIELD label
CALL apoc.cypher.run("MATCH (n:" + label + ") RETURN count(n) as count", {}) YIELD value
WITH label, value.count as count
ORDER BY count DESC
LIMIT 10
WITH collect({label: label, count: count}) as labelStats
RETURN "Node Labels" as check_name, "INFO" as status,
       "Top labels: " + toString(labelStats) as details,
       datetime() as timestamp;

// Check relationship type distribution (top 10)
CALL db.relationshipTypes() YIELD relationshipType
CALL apoc.cypher.run("MATCH ()-[r:" + relationshipType + "]->() RETURN count(r) as count", {}) YIELD value
WITH relationshipType, value.count as count
ORDER BY count DESC
LIMIT 10
WITH collect({type: relationshipType, count: count}) as relStats
RETURN "Relationship Types" as check_name, "INFO" as status,
       "Top types: " + toString(relStats) as details,
       datetime() as timestamp;

// Check database configuration
CALL dbms.listConfig() YIELD name, value
WHERE name IN ['dbms.memory.heap.initial_size', 'dbms.memory.heap.max_size', 
               'dbms.memory.pagecache.size', 'dbms.security.auth_enabled']
WITH collect({setting: name, value: value}) as configSettings
RETURN "Configuration" as check_name, "INFO" as status,
       "Key settings: " + toString(configSettings) as details,
       datetime() as timestamp;

// Final status summary
WITH datetime() as checkTime
RETURN "Health Check Complete" as check_name, "OK" as status,
       "All health checks completed at " + toString(checkTime) as details,
       checkTime as timestamp;