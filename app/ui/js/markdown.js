/*
 * Renderizador Markdown local e seguro.
 * Não usa CDN e nunca injeta HTML vindo do modelo: todo o texto é escapado
 * antes de aplicar formatação limitada. Links só aceitam http(s), mailto e âncoras.
 */
(function () {
  'use strict';

  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function sanitizeUrl(url) {
    var decoded = url.replace(/&amp;/g, '&').trim();
    var safe =
      /^https?:\/\//i.test(decoded) ||
      /^mailto:/i.test(decoded) ||
      /^#/.test(decoded) ||
      /^\/(?!\/)/.test(decoded);
    // Reject javascript:, data:, protocol-relative (//host) and control chars.
    if (
      !safe ||
      /javascript:/i.test(decoded) ||
      /^\/\//.test(decoded) ||
      /[\u0000-\u001f]/.test(decoded)
    ) {
      return null;
    }
    return escapeHtml(decoded);
  }

  function inline(text) {
    var codes = [];
    var links = [];

    // Inline code first (protected from further formatting).
    text = text.replace(/`([^`\n]+)`/g, function (_, code) {
      codes.push('<code>' + code + '</code>');
      return '\u0000C' + (codes.length - 1) + '\u0000';
    });

    // Markdown links [text](url)
    text = text.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (match, label, url) {
      var safe = sanitizeUrl(url);
      if (!safe) return match;
      links.push('<a href="' + safe + '" target="_blank" rel="noopener noreferrer">' + label + '</a>');
      return '\u0000L' + (links.length - 1) + '\u0000';
    });

    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/__([^_]+)__/g, '<strong>$1</strong>');
    text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    text = text.replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>');
    text = text.replace(/~~([^~]+)~~/g, '<del>$1</del>');

    text = text.replace(/\u0000C(\d+)\u0000/g, function (_, i) { return codes[Number(i)]; });
    text = text.replace(/\u0000L(\d+)\u0000/g, function (_, i) { return links[Number(i)]; });
    return text;
  }

  // ---------- Matemática (KaTeX local, sem CDN) ----------
  // $$…$$ e \[…\] viram fórmulas em destaque; \(…\) e $…$ ficam na frase.
  // Regra do dinheiro para $…$: o $ de abertura não vem depois de letra ou
  // número (R$, US$) nem antes de espaço, e o de fechamento não vem depois de
  // espaço nem antes de dígito. Assim "R$ 10 e R$ 20" e "$5 e $8" ficam texto.
  var MATH_PATTERNS = [
    { re: /\$\$([\s\S]+?)\$\$/g, display: true },
    { re: /\\\[([\s\S]+?)\\\]/g, display: true },
    { re: /\\\(([^\n]+?)\\\)/g, display: false },
    { re: /(^|[^\\\w$])\$(?=[^\s$])((?:\\.|[^$\\\n])+?)(?<=[^\s\\])\$(?!\d)/g, display: false, lead: true },
  ];

  function renderMath(tex, display) {
    var source = tex.trim();
    if (window.katex && typeof window.katex.renderToString === 'function') {
      try {
        var html = window.katex.renderToString(source, {
          displayMode: display, throwOnError: false, trust: false, strict: 'ignore', output: 'htmlAndMathml',
        });
        return display ? '<div class="math-block">' + html + '</div>' : html;
      } catch (_) { /* cai no texto puro abaixo */ }
    }
    var delim = display ? '$$' : '$';
    return '<code class="math-fallback">' + escapeHtml(delim + source + delim) + '</code>';
  }

  function extractMath(text, maths) {
    // Inline code spans are not math: hide them while the patterns run.
    var spans = [];
    text = text.replace(/`[^`\n]+`/g, function (span) {
      spans.push(span);
      return '\u0000S' + (spans.length - 1) + '\u0000';
    });
    MATH_PATTERNS.forEach(function (p) {
      text = text.replace(p.re, function (match, a, b) {
        var lead = p.lead ? a : '';
        var tex = p.lead ? b : a;
        if (!tex.trim()) return match;
        maths.push({ html: renderMath(tex, p.display), display: p.display });
        var mark = '\u0000M' + (maths.length - 1) + '\u0000';
        // A display formula is a block of its own.
        return lead + (p.display ? '\n' + mark + '\n' : mark);
      });
    });
    return text.replace(/\u0000S(\d+)\u0000/g, function (_, i) { return spans[Number(i)]; });
  }

  function splitRow(row) {
    return row.replace(/^\|/, '').replace(/\|$/, '').split('|').map(function (c) { return c.trim(); });
  }

  function renderMarkdown(source) {
    var text = String(source == null ? '' : source).replace(/\r\n/g, '\n');
    var blocks = [];

    // Fenced code blocks are extracted BEFORE escaping the rest.
    text = text.replace(/```([A-Za-z0-9_+-]*)\n([\s\S]*?)```/g, function (_, lang, code) {
      var cls = lang ? ' class="language-' + escapeHtml(lang) + '"' : '';
      blocks.push('<pre><code' + cls + '>' + escapeHtml(code.replace(/\n$/, '')) + '</code></pre>');
      return '\u0000B' + (blocks.length - 1) + '\u0000';
    });

    var maths = [];
    text = extractMath(text, maths);
    text = escapeHtml(text);

    var lines = text.split('\n');
    var html = [];
    var paragraph = [];
    var listType = null;

    function closeParagraph() {
      if (paragraph.length) {
        html.push('<p>' + inline(paragraph.join('<br>')) + '</p>');
        paragraph = [];
      }
    }
    function closeList() {
      if (listType) {
        html.push('</' + listType + '>');
        listType = null;
      }
    }
    function closeAll() { closeParagraph(); closeList(); }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var trimmed = line.trim();

      if (!trimmed) { closeAll(); continue; }

      var blockMatch = trimmed.match(/^\u0000B(\d+)\u0000$/);
      if (blockMatch) {
        closeAll();
        html.push(blocks[Number(blockMatch[1])]);
        continue;
      }

      var mathMatch = trimmed.match(/^\u0000M(\d+)\u0000$/);
      if (mathMatch && maths[Number(mathMatch[1])].display) {
        closeAll();
        html.push(trimmed);  // trocado pela fórmula no fim
        continue;
      }

      var heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        closeAll();
        var level = heading[1].length;
        html.push('<h' + level + '>' + inline(heading[2]) + '</h' + level + '>');
        continue;
      }

      if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
        closeAll();
        html.push('<hr>');
        continue;
      }

      // Tables: a header row, a |---|:---:| separator, then body rows.
      var next = (lines[i + 1] || '').trim();
      if (/^\|.*\|$/.test(trimmed) && /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$/.test(next)) {
        closeAll();
        var aligns = splitRow(next).map(function (c) {
          return /^:-+:$/.test(c) ? 'center' : /-:$/.test(c) ? 'right' : '';
        });
        var cell = function (tag, c, k) {
          var a = aligns[k] ? ' style="text-align:' + aligns[k] + '"' : '';
          return '<' + tag + a + '>' + inline(c) + '</' + tag + '>';
        };
        var table = '<table><thead><tr>' +
          splitRow(trimmed).map(function (c, k) { return cell('th', c, k); }).join('') +
          '</tr></thead><tbody>';
        i += 2;
        while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) {
          table += '<tr>' + splitRow(lines[i].trim()).map(function (c, k) { return cell('td', c, k); }).join('') + '</tr>';
          i++;
        }
        i--;
        html.push(table + '</tbody></table>');
        continue;
      }

      var quote = trimmed.match(/^&gt;\s?(.*)$/);
      if (quote) {
        closeAll();
        html.push('<blockquote>' + inline(quote[1]) + '</blockquote>');
        continue;
      }

      var ul = trimmed.match(/^[-*+]\s+(.*)$/);
      var ol = trimmed.match(/^\d+[.)]\s+(.*)$/);
      if (ul || ol) {
        closeParagraph();
        var wanted = ul ? 'ul' : 'ol';
        if (listType !== wanted) {
          closeList();
          html.push('<' + wanted + '>');
          listType = wanted;
        }
        html.push('<li>' + inline((ul || ol)[1]) + '</li>');
        continue;
      }

      closeList();
      paragraph.push(trimmed);
    }
    closeAll();

    var rendered = html.join('\n');
    rendered = rendered.replace(/\u0000B(\d+)\u0000/g, function (_, n) { return blocks[Number(n)]; });
    rendered = rendered.replace(/\u0000M(\d+)\u0000/g, function (_, n) { return maths[Number(n)].html; });
    return rendered;
  }

  window.escapeHtml = escapeHtml;
  window.renderMarkdown = renderMarkdown;
})();
