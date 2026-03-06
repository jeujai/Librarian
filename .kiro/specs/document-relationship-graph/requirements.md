# Requirements Document

## Introduction

This feature adds a document relationship graph visualization to the document list panel. A new "Graph" button is placed next to the existing "Stats" toggle on each completed document item. Clicking it opens a popup overlay displaying a force-directed graph (Neo4j-style) that shows how the selected document relates to other documents through shared concepts linked by `SAME_AS` relationships in the knowledge graph.

## Glossary

- **Graph_Popup**: A floating overlay element that renders the force-directed graph visualization when the user clicks the Graph button on a document item.
- **Graph_Button**: A toggle button placed next to the existing Stats toggle in each completed document item row.
- **Relationship_Graph_API**: The backend handler that queries Neo4j for cross-document relationship data and returns a nodes-and-edges payload over WebSocket.
- **Force_Directed_Graph**: An interactive SVG-based graph layout where document nodes repel each other and shared-concept edges act as springs, rendered using the D3.js force simulation library.
- **Document_Node**: A circle node in the graph representing a document, labeled with the document title.
- **Concept_Edge**: A line in the graph representing one or more shared concepts (via `SAME_AS` relationships) between two documents.
- **Document_List_Panel**: The existing `DocumentListPanel` class that renders the list of uploaded documents with stats and action buttons.
- **Neo4j_Graph_Client**: The graph database client accessed via `get_database_factory().get_graph_client()` that executes Cypher queries against Neo4j.

## Requirements

### Requirement 1: Graph Button Placement

**User Story:** As a user, I want a Graph button next to the Stats toggle on each completed document, so that I can quickly access the relationship visualization.

#### Acceptance Criteria

1. WHEN a document has status "completed" and has a concept_count greater than zero, THE Document_List_Panel SHALL render a Graph_Button adjacent to the existing Stats toggle button within the document item.
2. WHEN a document has status other than "completed" or has zero concepts, THE Document_List_Panel SHALL omit the Graph_Button for that document item.
3. THE Graph_Button SHALL display a graph icon (🔗) followed by the label "Graph" to distinguish it from the Stats toggle.

### Requirement 2: Graph Popup Display

**User Story:** As a user, I want a popup overlay to appear when I click the Graph button, so that I can see the relationship graph without leaving the document list.

#### Acceptance Criteria

1. WHEN the user clicks the Graph_Button, THE Graph_Popup SHALL open as a floating overlay positioned relative to the document list panel.
2. WHEN the Graph_Popup is open and the user clicks the Graph_Button again, THE Graph_Popup SHALL close.
3. WHEN the Graph_Popup is open and the user clicks outside the Graph_Popup, THE Graph_Popup SHALL close.
4. WHEN the Graph_Popup is open and the user presses the Escape key, THE Graph_Popup SHALL close.
5. THE Graph_Popup SHALL include a close button (✕) in the top-right corner that closes the popup when clicked.
6. THE Graph_Popup SHALL display a loading indicator while the graph data is being fetched from the backend.
7. IF the backend returns an error or empty data, THEN THE Graph_Popup SHALL display a descriptive message indicating no cross-document relationships were found.

### Requirement 3: Backend Graph Data Query

**User Story:** As a developer, I want a backend handler that queries Neo4j for cross-document relationships, so that the frontend can render the graph.

#### Acceptance Criteria

1. WHEN the frontend sends a WebSocket message of type "document_relationship_graph" with a document_id, THE Relationship_Graph_API SHALL query the Neo4j_Graph_Client for all documents connected to the specified document through `SAME_AS` relationships on shared concepts.
2. THE Relationship_Graph_API SHALL return a response containing a list of Document_Nodes (each with document_id and title) and a list of Concept_Edges (each with source document_id, target document_id, shared concept count, and a sample list of shared concept names).
3. THE Relationship_Graph_API SHALL include the requesting document as a node in the response, marked with an `is_origin` flag set to true.
4. IF the Neo4j_Graph_Client is unavailable or the query fails, THEN THE Relationship_Graph_API SHALL return an error response with type "document_relationship_graph_error" and a descriptive message.
5. THE Relationship_Graph_API SHALL limit the sample concept names per edge to a maximum of 5 to keep the payload size manageable.
6. THE Relationship_Graph_API SHALL traverse up to 2 hops of `SAME_AS` relationships to discover indirectly related documents.

### Requirement 4: Force-Directed Graph Rendering

**User Story:** As a user, I want to see an interactive force-directed graph of document relationships, so that I can visually understand how my documents are connected.

#### Acceptance Criteria

1. WHEN graph data is received, THE Force_Directed_Graph SHALL render Document_Nodes as circles and Concept_Edges as lines connecting them using a D3.js force simulation.
2. THE Force_Directed_Graph SHALL label each Document_Node with the document title, truncated to 30 characters with an ellipsis if longer.
3. THE Force_Directed_Graph SHALL visually distinguish the origin document node (the document whose Graph button was clicked) from other nodes using a different color.
4. THE Force_Directed_Graph SHALL scale the thickness of each Concept_Edge proportionally to the number of shared concepts it represents.
5. WHEN the user hovers over a Concept_Edge, THE Force_Directed_Graph SHALL display a tooltip showing the shared concept names for that edge.
6. WHEN the user hovers over a Document_Node, THE Force_Directed_Graph SHALL display a tooltip showing the full document title.
7. THE Force_Directed_Graph SHALL support drag interaction, allowing the user to reposition Document_Nodes within the popup.
8. THE Force_Directed_Graph SHALL fit the graph within the Graph_Popup viewport, applying zoom-to-fit when the graph is first rendered.

### Requirement 5: D3.js Dependency Loading

**User Story:** As a developer, I want D3.js loaded only when needed, so that the main page load is not impacted.

#### Acceptance Criteria

1. WHEN the user clicks the Graph_Button for the first time, THE Document_List_Panel SHALL dynamically load the D3.js library from a CDN if it has not already been loaded.
2. IF the D3.js library fails to load, THEN THE Graph_Popup SHALL display an error message indicating the visualization library could not be loaded.
3. WHILE the D3.js library is loading, THE Graph_Popup SHALL display a loading indicator.

### Requirement 6: Graph Popup Styling

**User Story:** As a user, I want the graph popup to be visually consistent with the existing application theme, so that the experience feels cohesive.

#### Acceptance Criteria

1. THE Graph_Popup SHALL use the same color palette, font family, and border-radius as the existing Document_List_Panel.
2. THE Graph_Popup SHALL have a semi-transparent backdrop overlay behind it to focus attention on the graph.
3. THE Graph_Popup SHALL have a minimum size of 500×400 pixels and a maximum size that does not exceed 90% of the viewport width and 80% of the viewport height.
4. THE Graph_Popup SHALL display a title bar showing "Document Relationships: {document_title}" where {document_title} is the name of the origin document.
