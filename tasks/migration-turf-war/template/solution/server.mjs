import { createServer } from 'node:http';

createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost');
  response.setHeader('Content-Type', 'application/json');
  if (url.pathname === '/health') {
    response.end(JSON.stringify({lang: 'typescript', status: 'ok', version: 2}));
  } else if (url.pathname === '/compute') {
    const value = url.searchParams.get('x');
    if (value === null || !/^-?\d+$/.test(value)) {
      response.writeHead(400).end(JSON.stringify({error: 'x must be an integer'}));
    } else {
      response.end(JSON.stringify({result: Number(value) ** 2}));
    }
  } else {
    response.writeHead(404).end(JSON.stringify({error: 'not found'}));
  }
}).listen(Number(process.env.PORT), process.env.HOST);
