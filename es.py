#!/usr/bin/env python3
from typing import List, Any, Dict, Optional, Iterator
import time
import traceback
import elasticsearch.helpers # type: ignore
from elasticsearch import Elasticsearch
from db import FicInfo
from oil import oil
import authentications as a

logFileName = f'./es.log'

def plog(msg: str) -> None:
	global logFileName
	print(f'{int(time.time())}|{msg}')

def connect() -> Any:
	return Elasticsearch(hosts=["es"], http_auth=('elastic', 'espass'))

def dropIndex(es: Any) -> None:
	try:
		es.indices.delete(index='fi')
	except:
		pass

def createIndex(es: Any) -> None:
	try:
		es.indices.create(index='fi', body={
				'settings': {
					'analysis': {
						'analyzer': {
							'default': { 'type': 'standard' },
						},
					},
				},
				'mappings': {
					'properties': {
						'urlId': { 'type': 'text' },
						'created': { 'type': 'date' },
						'updated': { 'type': 'date' },
						'title': { 'type': 'text' },
						'author': { 'type': 'text' },
						'chapters': { 'type': 'long' },
						'words': { 'type': 'long' },
						'description': { 'type': 'text' },
						'ficCreated': { 'type': 'date' },
						'ficUpdated': { 'type': 'date' },
						'status': { 'type': 'text' },
						'source': { 'type': 'text' },
					},
				},
			})
	except:
		pass

def search(q: str, limit: int = 10) -> List[FicInfo]:
	try:
		es = connect()
		res = es.search(index="fi", body={
				"query": {
					"multi_match": {
						"query": q,
						"analyzer": 'standard',
					},
				}
			}, size=limit)
		print(f"es.search({q}) => {res['hits']['total']['value']} hits")
		fis: List[FicInfo] = []
		for hit in res['hits']['hits']:
			if len(fis) >= limit:
				break
			fis += FicInfo.select(hit['_id'])
		return fis[:limit]
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('fes.search({q}): ^ something went wrong searching es data :/')
		return [] # TODO

def save(fi: FicInfo) -> None:
	es = connect()
	r = handleFicInfo(fi)
	_id = r.pop('_id', fi.id)
	es.index(index='fi', id=_id, body=r)

def handleFicInfo(fi: FicInfo) -> Dict[str, Any]:
	_id = fi.id
	r = dict(fi.__dict__)
	r['urlId'] = r.pop('id', None)
	r['_id'] = _id
	return r

def generateFicInfo() -> Iterator[Dict[str, Any]]:
	for fi in FicInfo.select():
		yield handleFicInfo(fi)

def main(argv: List[str]) -> int:
	if len(sys.argv) not in {1}:
		print(f"usage: {sys.argv[0]}")
		return 1

	es = connect()
	plog(f"using log {logFileName}")
	#dropIndex(es)
	createIndex(es)

	success = False
	cnt = 0
	for t in range(10):
		if success:
			break
		if t > 0:
			time.sleep(5)
		try:
			elasticsearch.helpers.bulk(client=es, index='fi',
					actions=generateFicInfo())
			cnt += 1
			success = True
		except SystemExit as e:
			raise
		except:
			plog(f"  trouble")
			plog(traceback.format_exc())
	if not success:
		plog(f"  permanent trouble")
		raise Exception('block failed')

	return 0

if __name__ == '__main__':
	import sys
	sys.exit(main(sys.argv))

