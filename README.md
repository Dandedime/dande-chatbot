# Setup

You'll need to put the secrets file in `.streamlit/secrets.toml`

Requirements can be installed by running 

    pip install -r requirements.txt

# Chatbot

## Running the chatbot

To run the chatbot locally

`streamlit run dandy_app.py`

By default it will run chatbot version that connects to neo4j, but an argument of `sql` can be included to have it run with snowflake

`streamlit run dandy_app.py sql`

## Using the chatbot

The chatbot performs best when the user queries are clear and specific and utilize language it is already to use to. For example, using the names of the entity types (like "individual", "organization", "corporation") and relationship types (like "contribution" and "violation") that it is familiar with can help make the intent more apparent.

## Chatbot prompts

Prompts used by the chatbot live in `prompt_contexts/`. For example the prompt used for doing LLM-based entity resolution is `prompt_contexts/entity_resolution.txt` or for the neo4j chatbot is `prompt_contexts/neo4j.txt`. Prompts can easily be edited by editing these text files.  `build_prompts.py` contains python classes for loading and handling these prompts. `conversation.py` contains python classes for handling conversations that use these prompts.

# Neo4j

## Data classes

`data_structures/classes.py` defines standard data types that will be used in neo4j. For example there are classes for Individual, Corporation, and Organization as well as for relationships like Contribution, Identity, and Violation. These classes define the properties for each data type that will be placed in neo4j (things like name, address, date, etc). They also handle how to convert an instance of these data types into a text description that will be embedded for entity resolution.

## Populating neo4j graph db

Tables from snowflake or csvs can be piped into the graph db via `populate_neo4j.py` script. This script will loop through the rows in the table, use a provided key to extract entities and relationships from each row, upsert these into the graph db, and perform basic entity resolution which adds identity relationships between candidate entity matches. Some identity clusters will be collapsed during this process if they meet the provided threshold, the remaining identity edges are maintained for possible future entity resolution.

To run a table through this pipeline use the following command

    python populate_neo4j.py --table-key PATH_TO_KEY_JSON --csv_file OPTIONAL_PATH_TO_CSV

If a csv_file is provided any query present in the table key will be ignored in favor of using the data in the csv. I've found it's more convenient to use csv_files for continuing the pipeline if the connection fails part way through. Snowlfake query results do not have a deterministic order so it's more challenging to continue in those cases. To continue with a csv file we can use the `row_index` argument to specify the row number of the csv to start at

    python populate_neo4j.py --table-key PATH_TO_KEY_JSON --csv_file PATH_TO_CSV --row_index START_ROW_INDEX

### Table Keys

A table key must be given to the populate script that describes the entities and relationships present in each row. These keys are defined as json files stored in `table_keys/`. The basic structure of one of these jsons will look like

    {
        "table_name": TABLE_NAME,
	"query": QUERY,
	"entities": [
            {
                "entity_type":  ENTITY_TYPE,
                "fields": {
                    ENTITY_TYPE: {
                        ENTITY_FIELD_NAME1: ENTITY_COLUMN_NAME1,
                        ENTITY_FIELD_NAME2: ENTITY_COLUMN_NAME2,
                        ...
                    }
             },
             ...
         ],
         "relationships": [
             {
                 "relationship_type": RELATIONSHIP_TYPE,
                 "fields": {
                     REL_FIELD_NAME1: REL_COLUMN_NAME1,
                     REL_FIELD_NAME2: REL_COLUMN_NAME2,
                     ...
                  },
                  "source_entity": SRC_ENTITY_IDX,
                  "terminal_entity": TERM_ENTITY_IDS
             },
             ...
          ]
    }

Here the query is optionally present, if given it will use the result of that query in the pipeline, otherwise it will simply select all data from the table. Entities present in each row are provided as a list, defining the `entity_type`, then given the `entity_type` define a mapping from the standard entity field name as defined in `data_structures/classes.py` to the column names of the table being processed.  The relationships part of the json is structured similiarly, also giving the indices with respect to the entity list of the source entity and the terminal entity of the relationship.  Here is an example json for the corporate violations table:

    {
        "table_name": "corporate_regulatory_violations",
	"entities":
            [
		{
                    "entity_type": "corporation",
                    "fields": {
                        "corporation": {
                            "name": "COMPANY",
                            "parent_company": "PARENT_COMPANY",
                            "industry": "INDUSTRY"
                        }
                    }
		},
		{
       	            "entity_type": "agency",
                    "fields": {
                        "agency": {
                            "name": "AGENCY"
                        }
                    }
                }
            ],
	"relationships":
            [
                {
                   "relationship_type": "violation",
                   "fields": {
                       "violation_type": "OFFENSE_TYPE",
                       "year": "YEAR",
                       "amount": "AMOUNT"
                   },
                   "source_entity": 0,
                   "terminal_entity": 1
	        }
            ]
    }

Note there are cases when the entity type is dynamic depending on a value of a particular column. To handle these cases the `entity_type` field in the json can be structured as in the following example

    "entity_type": [
        {
            "column": "CONTRIBUTOR_TYPE",
            "value": "individual",
            "type": "individual"
        },
        {
            "column": "CONTRIBUTOR_TYPE",
            "value": "org",
            "type": "organization"
        }
    ]

Here we see that if the column in the table called `CONTRIBUTOR_TYPE` has value `individual` then the entity type is individual. If the same column has value `org` then the entity type is organization.

### Entity Resolution

Using the entity embedder which leverages a text embedding model from Hugging Face to separately embed the entire description of an entity and just the name of the entity, an overall score and a name score is assigned to each potential entity match. Theresholds for score and name score  can be set above which an identity relationship is added between the entities. Additional thresholds are set for each above which nodes are destructively collapsed into each other, preserving any relationships to other nodes.  These values can be adjusted when running the script as

    python populate_neo4j.py --table-key PATH_TO_JSON --score-min 0.97 --name-score-min 0.98 --score-collapse-min 0.99 --name-score-collapse-min 0.99

#### Embedding

Currently the text descriptions of entities are embedded via a model from HuggingFace. The custom embedding defined in `embedding.py` uses this model to separately embed a text description stating the entity type and its name and the text describing the values of the entity's properties. These two vectors are concatenated to form a single embedding. This separation is done so that we can compute an overall embedding similarity score and a name-specific score to put separate cosntraints on each. No matter how similiar the properties of two entities are, if their name and entity type are not sufficiently similar then they are very unlikely to refer to the same entity.

#### Neighbor Score

After populating the graph db a neighbor score is assigned to identity edges which for a given relationship type computes an intersection-over-union for relationships of the nodes. For example if the relationship type in question is contribution, then it will look at the total number of entities contributed to by node A and by node B, and the number of those that both contributed to. The logic is that two nodes are more likely to refer to the same entity if they associate with the same entities in the same manner.

#### LLM-based Entity Resolution

Additional analysis to support entity resolution can be performed using an LLM. `llm_resolve.py` defines a class that grabs identity candidate clusters from the graph (based on whatever score thresholds) and feeds them to the LLM. The LLM is given a prompt defined in `prompt_contexts/entity_resolution.txt` which instructs it to break the provided cluster down into sub-clusters referring to the same entity and assign each a score. If it decides the provided cluster most likely does all refer to the same entity there will be a single sub-cluster and a single confidence score for the whole set. The identity edges between each node of each sub-cluster receive an `llm_score`.  This process can be run with a command such as the following

    python llm_resolve.py --score-min 0.97 --name-score-min 0.97 --neighbor-score-min 0.5

#### Destructive Identity Cluster Collapsing

At any time further destructuve consolidation of entities can be performed using whatever perscribed score conditions. For example

    python resolve.py --score-min 0.97 --name-score-min 0.98 --llm-score-min 0.8
