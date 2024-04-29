from neo4j import GraphDatabase
from data_structures import Entity, Relationship
from dataclasses import asdict


class Neo4jConnection:

    def __init__(self, uri, user, pwd):
        self.__uri = uri
        self.__user = user
        self.__pwd = pwd
        self.__driver = None
        try:
            self.__driver = GraphDatabase.driver(self.__uri, auth=(self.__user, self.__pwd))
        except Exception as e:
            print("Failed to create the driver:", e)

    def _get_session(self):
        return self.__driver.session() 

    def close(self):
        if self.__driver is not None:
            self.__driver.close()

    def query(self, query, parameters=None, db=None):
        session = self._get_session()
        response = list(session.run(query, parameters))
        if session is not None:
            session.close()

    def create_node(self, entity: Entity):
        session = self._get_session()
        dict_str = ", ".join([f"{key}: '{val}'" for key, val in
                              asdict(entity).items() if val is not None])
        query = f"CREATE (n:{entity.entity_type} {{{dict_str}}})"
        res = session.run(query)
        session.close()
        return res

    def create_edge(self, relationship: Relationship, origin_entity: Entity,
                    terminal_entity: Entity):
        session = self._get_session()
        property_str = ", ".join([f"r.{key}='val'" for key, val in
                                 asdict(relationship).items() if val is not
                                 None])
        query = f"MATCH (a:{origin_entity.entity_type}), "\
        f"(b:{terminal_entity.entity_type}) WHERE a.id = $id1 AND b.id = $id2"\
        f" CREATE (a)-[r:{relationship.relationship_type}]->(b) "\
        f" SET {property_str}"
        res = session.run(query, id1=origin_entity.id, id2=terminal_entity.id)
        session.close()
        return res
