from data import Entity


class EntityResolution:

    def __init__(self, pinecone_index, embedding=None):
        self.pinecone_index = pinecone_index
        if embedding is None:
            embedding = OpenAIEmbedding()
        self.embedding = embedding

        # threshold and stuff

    def resolve(self, entity_data: Entity):
        """
        Args:
            entity_data: Entity class instance containing data for entity to be
                rseolved
        Returns:
            Pinecone id either referring to an existing entity or for a newly
                upserted entity
        """
        data_str = self._format_data_str(entity_data)
        vector = self.embed(data_str)
        best_match_entity = self.pinecone_index.query(vector=vector, top_k=1)

    @staticmethod
    def _format_data_str(entity_data):
        data_str = f"{entity_data.entity_type} named {entity_data.name} with "
        
        field_strs = [f"{field} of {value}" for field, value in
                      asdict(entity_data).items() if field not in
                      ["entity_type", "name"]]
        data_str += ", ".join(field_strs)
        return data_str


    #potentially some llm verificatino stuff
