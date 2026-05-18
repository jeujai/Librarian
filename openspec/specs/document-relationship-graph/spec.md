## Purpose

This feature adds a document relationship graph visualization to the document list panel. A new "Graph" button is placed next to the existing "Stats" toggle on each completed document item. Clicking it opens a popup overlay displaying a force-directed graph (Neo4j-style) that shows how the selected document relates to other documents through shared concepts linked by `SAME_AS` relationships in the knowledge graph.


### Key Terms
- **Graph_Popup**: A floating overlay element that renders the force-directed graph visualization when the user clicks the Graph button on a document item.
- **Graph_Button**: A toggle button placed next to the existing Stats toggle in each completed document item row.
- **Relationship_Graph_API**: The backend handler that queries Neo4j for cross-document relationship data and returns a nodes-and-edges payload over WebSocket.
- **Force_Directed_Graph**: An interactive SVG-based graph layout where document nodes repel each other and shared-concept edges act as springs, rendered using the D3.js force simulation library.
- **Document_Node**: A circle node in the graph representing a document, labeled with the document title.
- **Concept_Edge**: A line in the graph representing one or more shared concepts (via `SAME_AS` relationships) between two documents.
- **Document_List_Panel**: The existing `DocumentListPanel` class that renders the list of uploaded documents with stats and action buttons.
- **Neo4j_Graph_Client**: The graph database client accessed via `get_database_factory().get_graph_client()` that executes Cypher queries against Neo4j.

## Requirements

### Requirement: Graph Button Placement

The system SHALL support: As a user, I want a Graph button next to the Stats toggle on each completed document, so that I can quickly access the relationship visualization.

#### Scenario: WHEN a document has status "completed" and has a concept_cou

- **THEN** WHEN a document has status "completed" and has a concept_count greater than zero, THE Document_List_Panel SHALL render a Graph_Button adjacent to the existing Stats toggle button within the document item.

#### Scenario: WHEN a document has status other than "completed" or has zer

- **THEN** WHEN a document has status other than "completed" or has zero concepts, THE Document_List_Panel SHALL omit the Graph_Button for that document item.

#### Scenario: THE Graph_Button SHALL display a graph icon (🔗) followed by

- **THEN** THE Graph_Button SHALL display a graph icon (🔗) followed by the label "Graph" to distinguish it from the Stats toggle.

### Requirement: Graph Popup Display

The system SHALL support: As a user, I want a popup overlay to appear when I click the Graph button, so that I can see the relationship graph without leaving the document list.

#### Scenario: WHEN the user clicks the Graph_Button, THE Graph_Popup SHALL

- **THEN** WHEN the user clicks the Graph_Button, THE Graph_Popup SHALL open as a floating overlay positioned relative to the document list panel.

#### Scenario: WHEN the Graph_Popup is open and the user clicks the Graph_B

- **THEN** WHEN the Graph_Popup is open and the user clicks the Graph_Button again, THE Graph_Popup SHALL close.

#### Scenario: WHEN the Graph_Popup is open and the user clicks outside the

- **THEN** WHEN the Graph_Popup is open and the user clicks outside the Graph_Popup, THE Graph_Popup SHALL close.

#### Scenario: WHEN the Graph_Popup is open and the user presses the Escape

- **THEN** WHEN the Graph_Popup is open and the user presses the Escape key, THE Graph_Popup SHALL close.

#### Scenario: THE Graph_Popup SHALL include a close button (✕) in the top-

- **THEN** THE Graph_Popup SHALL include a close button (✕) in the top-right corner that closes the popup when clicked.

#### Scenario: THE Graph_Popup SHALL display a loading indicator while the

- **THEN** THE Graph_Popup SHALL display a loading indicator while the graph data is being fetched from the backend.

#### Scenario: IF the backend returns an error or empty data, THEN THE Grap

- **GIVEN** the backend returns an error or empty data
- **THEN** IF the backend returns an error or empty data, THEN THE Graph_Popup SHALL display a descriptive message indicating no cross-document relationships were found.

### Requirement: Backend Graph Data Query

The system SHALL support: As a developer, I want a backend handler that queries Neo4j for cross-document relationships, so that the frontend can render the graph.

#### Scenario: WHEN the frontend sends a WebSocket message of type "documen

- **THEN** WHEN the frontend sends a WebSocket message of type "document_relationship_graph" with a document_id, THE Relationship_Graph_API SHALL query the Neo4j_Graph_Client for all documents connected to the specified document through `SAME_AS` relationships on shared concepts.

#### Scenario: THE Relationship_Graph_API SHALL return a response containin

- **THEN** THE Relationship_Graph_API SHALL return a response containing a list of Document_Nodes (each with document_id and title) and a list of Concept_Edges (each with source document_id, target document_id, shared concept count, and a sample list of shared concept names).

#### Scenario: THE Relationship_Graph_API SHALL include the requesting docu

- **THEN** THE Relationship_Graph_API SHALL include the requesting document as a node in the response, marked with an `is_origin` flag set to true.

#### Scenario: IF the Neo4j_Graph_Client is unavailable or the query fails,

- **GIVEN** the Neo4j_Graph_Client is unavailable or the query fails
- **THEN** IF the Neo4j_Graph_Client is unavailable or the query fails, THEN THE Relationship_Graph_API SHALL return an error response with type "document_relationship_graph_error" and a descriptive message.

#### Scenario: THE Relationship_Graph_API SHALL limit the sample concept na

- **THEN** THE Relationship_Graph_API SHALL limit the sample concept names per edge to a maximum of 5 to keep the payload size manageable.

#### Scenario: THE Relationship_Graph_API SHALL traverse up to 2 hops of `S

- **THEN** THE Relationship_Graph_API SHALL traverse up to 2 hops of `SAME_AS` relationships to discover indirectly related documents.

### Requirement: Force-Directed Graph Rendering

The system SHALL support: As a user, I want to see an interactive force-directed graph of document relationships, so that I can visually understand how my documents are connected.

#### Scenario: WHEN graph data is received, THE Force_Directed_Graph SHALL

- **THEN** WHEN graph data is received, THE Force_Directed_Graph SHALL render Document_Nodes as circles and Concept_Edges as lines connecting them using a D3.js force simulation.

#### Scenario: THE Force_Directed_Graph SHALL label each Document_Node with

- **THEN** THE Force_Directed_Graph SHALL label each Document_Node with the document title, truncated to 30 characters with an ellipsis if longer.

#### Scenario: THE Force_Directed_Graph SHALL visually distinguish the orig

- **THEN** THE Force_Directed_Graph SHALL visually distinguish the origin document node (the document whose Graph button was clicked) from other nodes using a different color.

#### Scenario: THE Force_Directed_Graph SHALL scale the thickness of each C

- **THEN** THE Force_Directed_Graph SHALL scale the thickness of each Concept_Edge proportionally to the number of shared concepts it represents.

#### Scenario: WHEN the user hovers over a Concept_Edge, THE Force_Directed

- **THEN** WHEN the user hovers over a Concept_Edge, THE Force_Directed_Graph SHALL display a tooltip showing the shared concept names for that edge.

#### Scenario: WHEN the user hovers over a Document_Node, THE Force_Directe

- **THEN** WHEN the user hovers over a Document_Node, THE Force_Directed_Graph SHALL display a tooltip showing the full document title.

#### Scenario: THE Force_Directed_Graph SHALL support drag interaction, all

- **THEN** THE Force_Directed_Graph SHALL support drag interaction, allowing the user to reposition Document_Nodes within the popup.

#### Scenario: THE Force_Directed_Graph SHALL fit the graph within the Grap

- **THEN** THE Force_Directed_Graph SHALL fit the graph within the Graph_Popup viewport, applying zoom-to-fit when the graph is first rendered.

### Requirement: D3.js Dependency Loading

The system SHALL support: As a developer, I want D3.js loaded only when needed, so that the main page load is not impacted.

#### Scenario: WHEN the user clicks the Graph_Button for the first time, TH

- **THEN** WHEN the user clicks the Graph_Button for the first time, THE Document_List_Panel SHALL dynamically load the D3.js library from a CDN if it has not already been loaded.

#### Scenario: IF the D3.js library fails to load, THEN THE Graph_Popup SHA

- **GIVEN** the D3.js library fails to load
- **THEN** IF the D3.js library fails to load, THEN THE Graph_Popup SHALL display an error message indicating the visualization library could not be loaded.

#### Scenario: WHILE the D3.js library is loading, THE Graph_Popup SHALL di

- **THEN** WHILE the D3.js library is loading, THE Graph_Popup SHALL display a loading indicator.

### Requirement: Graph Popup Styling

The system SHALL support: As a user, I want the graph popup to be visually consistent with the existing application theme, so that the experience feels cohesive.

#### Scenario: THE Graph_Popup SHALL use the same color palette, font famil

- **THEN** THE Graph_Popup SHALL use the same color palette, font family, and border-radius as the existing Document_List_Panel.

#### Scenario: THE Graph_Popup SHALL have a semi-transparent backdrop overl

- **THEN** THE Graph_Popup SHALL have a semi-transparent backdrop overlay behind it to focus attention on the graph.

#### Scenario: THE Graph_Popup SHALL have a minimum size of 500×400 pixels

- **THEN** THE Graph_Popup SHALL have a minimum size of 500×400 pixels and a maximum size that does not exceed 90% of the viewport width and 80% of the viewport height.

#### Scenario: THE Graph_Popup SHALL display a title bar showing "Document

- **THEN** THE Graph_Popup SHALL display a title bar showing "Document Relationships: {document_title}" where {document_title} is the name of the origin document.
