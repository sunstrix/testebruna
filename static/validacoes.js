/**
 * validacoes.js — CP FANI | Essência RH
 * Validação de CPF, e-mail e máscaras de data/telefone/CEP
 * Incluir em todos os formulários: <script src="/static/validacoes.js"></script>
 */

// =============================================================================
// 1. MÁSCARA DE DATA — Converte o input[type=date] para exibição BR (DD/MM/AAAA)
// =============================================================================
function aplicarMascaraData() {
    // Busca todos os inputs de data da página
    document.querySelectorAll('input[type="date"]').forEach(input => {

        // Força a localização visual para pt-BR onde o navegador suportar
        input.setAttribute('lang', 'pt-BR');

        // Wrapper visual: cria um input de texto visível ao lado do date oculto
        // Isso garante DD/MM/AAAA independente do navegador ou sistema operacional
        const wrapper = document.createElement('div');
        wrapper.style.position = 'relative';
        input.parentNode.insertBefore(wrapper, input);

        // Cria o input visual formatado em BR
        const inputVisual = document.createElement('input');
        inputVisual.type = 'text';
        inputVisual.placeholder = 'DD/MM/AAAA';
        inputVisual.maxLength = 10;
        inputVisual.className = input.className; // Herda as classes Bootstrap do original
        inputVisual.setAttribute('autocomplete', 'off');

        // Esconde o input original (mantido para envio correto via POST)
        input.style.display = 'none';
        wrapper.appendChild(inputVisual);
        wrapper.appendChild(input);

        // Se já tem valor (ex: edição), exibe formatado
        if (input.value) {
            const [ano, mes, dia] = input.value.split('-');
            inputVisual.value = `${dia}/${mes}/${ano}`;
        }

        // Aplica máscara enquanto o usuário digita
        inputVisual.addEventListener('input', function () {
            let val = this.value.replace(/\D/g, ''); // Remove tudo que não é dígito
            if (val.length > 2) val = val.slice(0, 2) + '/' + val.slice(2);
            if (val.length > 5) val = val.slice(0, 5) + '/' + val.slice(5);
            if (val.length > 10) val = val.slice(0, 10);
            this.value = val;

            // Sincroniza o input real (oculto) no formato ISO para o backend
            if (val.length === 10) {
                const [d, m, a] = val.split('/');
                if (d && m && a && a.length === 4) {
                    input.value = `${a}-${m}-${d}`;
                    inputVisual.classList.remove('is-invalid');
                    inputVisual.classList.add('is-valid');
                }
            } else {
                input.value = ''; // Limpa o oculto se incompleto
                inputVisual.classList.remove('is-valid');
            }
        });

        // Valida ao sair do campo
        inputVisual.addEventListener('blur', function () {
            if (this.value && this.value.length < 10) {
                inputVisual.classList.add('is-invalid');
                inputVisual.classList.remove('is-valid');
            }
        });
    });
}

// =============================================================================
// 2. VALIDAÇÃO E MÁSCARA DE CPF
//    Aplica a máscara 000.000.000-00 e valida os dígitos verificadores
// =============================================================================
function validarCPF(cpf) {
    cpf = cpf.replace(/\D/g, '');
    if (cpf.length !== 11) return false;
    if (/^(\d)\1+$/.test(cpf)) return false; // Rejeita sequências como 111.111.111-11

    // Cálculo do 1º dígito verificador
    let soma = 0;
    for (let i = 0; i < 9; i++) soma += parseInt(cpf[i]) * (10 - i);
    let digito1 = (soma * 10) % 11;
    if (digito1 === 10 || digito1 === 11) digito1 = 0;
    if (digito1 !== parseInt(cpf[9])) return false;

    // Cálculo do 2º dígito verificador
    soma = 0;
    for (let i = 0; i < 10; i++) soma += parseInt(cpf[i]) * (11 - i);
    let digito2 = (soma * 10) % 11;
    if (digito2 === 10 || digito2 === 11) digito2 = 0;
    if (digito2 !== parseInt(cpf[10])) return false;

    return true;
}

function aplicarMascaraCPF() {
    document.querySelectorAll('input[data-mask="cpf"]').forEach(input => {
        input.maxLength = 14;
        input.placeholder = '000.000.000-00';

        input.addEventListener('input', function () {
            let val = this.value.replace(/\D/g, '');
            if (val.length > 3)  val = val.slice(0, 3) + '.' + val.slice(3);
            if (val.length > 7)  val = val.slice(0, 7) + '.' + val.slice(7);
            if (val.length > 11) val = val.slice(0, 11) + '-' + val.slice(11);
            if (val.length > 14) val = val.slice(0, 14);
            this.value = val;
        });

        input.addEventListener('blur', function () {
            const cpfLimpo = this.value.replace(/\D/g, '');
            const feedback = this.nextElementSibling;

            if (cpfLimpo.length === 0) {
                this.classList.remove('is-valid', 'is-invalid');
                return;
            }

            if (validarCPF(cpfLimpo)) {
                this.classList.add('is-valid');
                this.classList.remove('is-invalid');
                if (feedback && feedback.classList.contains('invalid-feedback')) {
                    feedback.style.display = 'none';
                }
            } else {
                this.classList.add('is-invalid');
                this.classList.remove('is-valid');
                if (feedback && feedback.classList.contains('invalid-feedback')) {
                    feedback.style.display = 'block';
                }
            }
        });
    });
}

// =============================================================================
// 3. VALIDAÇÃO DE E-MAIL
//    Valida formato básico e domínio (exige pelo menos um ponto no domínio)
// =============================================================================
function aplicarValidacaoEmail() {
    document.querySelectorAll('input[type="email"], input[data-mask="email"]').forEach(input => {
        input.addEventListener('blur', function () {
            const regex = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
            const val = this.value.trim();

            if (val.length === 0) {
                this.classList.remove('is-valid', 'is-invalid');
                return;
            }

            if (regex.test(val)) {
                this.classList.add('is-valid');
                this.classList.remove('is-invalid');
            } else {
                this.classList.add('is-invalid');
                this.classList.remove('is-valid');
            }
        });
    });
}

// =============================================================================
// 4. MÁSCARA DE TELEFONE — (00) 00000-0000
// =============================================================================
function aplicarMascaraTelefone() {
    document.querySelectorAll('input[data-mask="telefone"]').forEach(input => {
        input.maxLength = 15;
        input.placeholder = '(00) 00000-0000';

        input.addEventListener('input', function () {
            let val = this.value.replace(/\D/g, '');
            if (val.length > 0)  val = '(' + val;
            if (val.length > 3)  val = val.slice(0, 3) + ') ' + val.slice(3);
            if (val.length > 10) val = val.slice(0, 10) + '-' + val.slice(10);
            if (val.length > 15) val = val.slice(0, 15);
            this.value = val;
        });
    });
}

// =============================================================================
// 5. MÁSCARA DE CEP — 00000-000
// =============================================================================
function aplicarMascaraCEP() {
    document.querySelectorAll('input[data-mask="cep"]').forEach(input => {
        input.maxLength = 9;
        input.placeholder = '00000-000';

        input.addEventListener('input', function () {
            let val = this.value.replace(/\D/g, '');
            if (val.length > 5) val = val.slice(0, 5) + '-' + val.slice(5);
            if (val.length > 9) val = val.slice(0, 9);
            this.value = val;
        });

        input.addEventListener('blur', function () {
            const cep = this.value.replace(/\D/g, '');
            if (cep.length !== 8) return;

            // Feedback visual enquanto busca
            input.classList.remove('is-valid', 'is-invalid');
            input.style.opacity = '0.6';

            fetch(`https://viacep.com.br/ws/${cep}/json/`)
                .then(r => r.json())
                .then(data => {
                    input.style.opacity = '1';

                    if (data.erro) {
                        input.classList.add('is-invalid');
                        return;
                    }

                    input.classList.add('is-valid');

                    // Helper: preenche qualquer campo pelo name, incluindo select
                    function preencherCampo(name, valor) {
                        if (!valor) return;
                        const el = document.querySelector(`[name="${name}"]`);
                        if (!el) return;
                        el.value = valor;

                        // Para selects (como endereco_estado), dispara change
                        // para garantir que frameworks detectem a mudança
                        el.dispatchEvent(new Event('change'));
                    }

                    preencherCampo('endereco_rua',    data.logradouro);
                    preencherCampo('endereco_bairro', data.bairro);
                    preencherCampo('endereco_cidade', data.localidade);
                    preencherCampo('endereco_estado', data.uf);
                })
                .catch(() => {
                    input.style.opacity = '1';
                    // Falha silenciosa — sem internet ou CEP não encontrado
                });
        });
    });
}

// =============================================================================
// 6. VALIDAÇÃO GERAL DO FORMULÁRIO antes do envio
//    Impede o submit se houver campos com is-invalid
// =============================================================================
function aplicarValidacaoFormulario() {
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function (e) {
            // Dispara o blur em todos os campos para garantir que as validações rodaram
            form.querySelectorAll('input[data-mask="cpf"]').forEach(el => el.dispatchEvent(new Event('blur')));
            form.querySelectorAll('input[type="email"], input[data-mask="email"]').forEach(el => el.dispatchEvent(new Event('blur')));

            // Bloqueia o envio se houver qualquer campo inválido
            if (form.querySelector('.is-invalid')) {
                e.preventDefault();
                e.stopPropagation();

                // Scroll suave até o primeiro erro
                const primeiroErro = form.querySelector('.is-invalid');
                primeiroErro.scrollIntoView({ behavior: 'smooth', block: 'center' });
                primeiroErro.focus();

                flash_inline(form, 'Corrija os campos destacados em vermelho antes de continuar.');
            }
        });
    });
}

// Exibe um alerta inline dentro do formulário (sem depender do Flask)
function flash_inline(form, mensagem) {
    let alerta = form.querySelector('.alerta-validacao-js');
    if (!alerta) {
        alerta = document.createElement('div');
        alerta.className = 'alert alert-danger alert-dismissible fade show alerta-validacao-js mt-3';
        alerta.innerHTML = `<i class="fa-solid fa-circle-exclamation me-2"></i>${mensagem}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
        form.prepend(alerta);
    }
}

// =============================================================================
// INICIALIZAÇÃO — Roda tudo ao carregar a página
// =============================================================================
document.addEventListener('DOMContentLoaded', function () {
    aplicarMascaraData();
    aplicarMascaraCPF();
    aplicarValidacaoEmail();
    aplicarMascaraTelefone();
    aplicarMascaraCEP();
    aplicarValidacaoFormulario();
});